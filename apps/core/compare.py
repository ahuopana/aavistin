"""Generic comparison of two entities of the same kind (ADR 0038).

Every comparable entity is reduced to a `Subject`: named sections of
``row label -> text`` pairs. `diff_subjects` then lines the two subjects up
section by section and marks each row same, changed, or present on one side
only. Nothing here knows what a regulation, requirement or question means;
labels come from the package content that produced the data.
"""

import re
from dataclasses import dataclass, field

from django.urls import reverse

from apps.assessments.evaluation import evaluate_configuration
from apps.assessments.models import Answer, Assessment, AssessmentStatus
from apps.assessments.templatetags.assessment_tags import choice_label as readable_choice
from apps.packages.models import PackageStatus, RequirementPackage
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareOption,
    SoftwareRelease,
)
from apps.products.services import editable_products, product_of
from apps.risk.models import RiskEntry
from apps.risk.resolution import register_for_configuration

SAME, CHANGED, ONLY_A, ONLY_B = "same", "changed", "only_a", "only_b"

KINDS = {
    "product": ("Product", Product),
    "hardware_variant": ("Hardware variant", HardwareVariant),
    "hardware_revision": ("Hardware revision", HardwareRevision),
    "software_release": ("Software release", SoftwareRelease),
    "software_option": ("Software option", SoftwareOption),
    "configuration": ("Configuration", Configuration),
    "assessment": ("Assessment", Assessment),
}

# Where each kind's product lives, for visibility filtering.
_PRODUCT_LOOKUP = {
    "product": "",
    "hardware_variant": "product",
    "hardware_revision": "hardware_variant__product",
    "software_release": "product",
    "software_option": "software_release__product",
    "configuration": "software_release__product",
    "assessment": "configuration__software_release__product",
}


@dataclass
class Subject:
    kind: str
    label: str
    url: str
    sections: list[tuple[str, dict[str, str]]] = field(default_factory=list)


@dataclass
class Row:
    label: str
    a: str | None
    b: str | None
    status: str


@dataclass
class SectionDiff:
    title: str
    rows: list[Row]

    @property
    def differences(self) -> int:
        return sum(1 for r in self.rows if r.status != SAME)


def fmt(value) -> str:
    if value is None or value == "":
        return "—"
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if isinstance(value, list | tuple | set):
        return ", ".join(sorted(fmt(v) for v in value)) or "—"
    return str(value)


_ID_SHAPED = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")


def display(value):
    """Readable form of a package id ("logical_delete" -> "Logical delete"),
    as the questionnaire shows choices; anything else is left alone."""
    if isinstance(value, str) and _ID_SHAPED.fullmatch(value):
        return readable_choice(value)
    if isinstance(value, list | tuple | set):
        return [display(v) for v in value]
    return value


def _markets(manager) -> str:
    return fmt(list(manager.values_list("code", flat=True)))


def _approval(obj) -> str:
    return "Approved" if getattr(obj, "is_approved", False) else "Not approved"


def question_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for package in RequirementPackage.objects.filter(status=PackageStatus.APPROVED):
        for question in package.content.get("questions", []):
            labels.setdefault(question["id"], question.get("label") or question["id"])
    return labels


def _owned_answers(**owner) -> dict[str, str]:
    labels = question_labels()
    rows = {}
    for answer in Answer.objects.filter(**owner).order_by("question_id"):
        text = fmt(display(answer.value))
        if answer.needs_confirmation:
            text += " (needs confirmation)"
        rows[labels.get(answer.question_id, answer.question_id)] = text
    return rows


def _risk_rows(entries) -> dict[str, str]:
    rows = {}
    for entry in entries:
        scope = "baseline" if entry.is_baseline else "scoped"
        rows[f"{entry.get_entry_type_display()}: {entry.label}"] = scope
    return rows


def _evaluation_sections(evaluation: dict) -> list[tuple[str, dict[str, str]]]:
    labels = question_labels()
    answers = {}
    for qid, answer in evaluation.get("resolved_answers", {}).items():
        text = fmt(display(answer.get("value")))
        origin = answer.get("origin")
        if origin:
            text += f" · {str(origin).replace('_', ' ')}"
        if answer.get("needs_confirmation"):
            text += " · needs confirmation"
        answers[labels.get(qid, qid)] = text

    contents = {
        p.pk: p.content
        for p in RequirementPackage.objects.filter(
            pk__in=[r.get("package_id") for r in evaluation.get("results", [])]
        )
    }
    scope, requirements = {}, {}
    for result in evaluation.get("results", []):
        content = contents.get(result.get("package_id"), {})
        source = result["source"]
        parts = [f"v{result['version']}", "in scope" if result["in_scope"] else "out of scope"]
        if result.get("classifications"):
            parts.append("class " + fmt(display(result["classifications"])))
        if result.get("role"):
            parts.append(f"role {fmt(display(result['role'])).lower()}")
        scope[source] = " · ".join(parts)
        by_id = {r["id"]: r for r in content.get("requirements", [])}
        for requirement_id in result.get("requirements", []):
            item = by_id.get(requirement_id, {})
            ref = f" ({item['ref']})" if item.get("ref") else ""
            requirements[f"{source}: {item.get('label') or requirement_id}{ref}"] = "in force"

    findings = {
        f"{f['source']}: {f['id']}": f"{display(f['level'])} — {f['message']}"
        for f in evaluation.get("findings", [])
    }
    return [
        ("Packages and scope", scope),
        ("Requirements in force", requirements),
        ("Findings", findings),
        ("Resolved answers", answers),
    ]


def build_subject(kind: str, obj) -> Subject:  # noqa: C901 - one branch per kind
    name = KINDS[kind][0]
    if kind == "product":
        subject = Subject(
            kind, f"{name} · {obj.name}", reverse("products:product_detail", args=[obj.pk])
        )
        subject.sections = [
            (
                "Details",
                {
                    "Family": fmt(obj.product_family.name),
                    "Status": obj.get_status_display(),
                    "Approval": _approval(obj),
                    "Description": fmt(obj.description),
                },
            ),
            (
                "Hardware variants",
                {v.name: _markets(v.target_markets) for v in obj.hw_variants.all()},
            ),
            (
                "Software releases",
                {
                    f"{r.name} {r.version}": _markets(r.target_markets)
                    for r in obj.sw_releases.all()
                },
            ),
            (
                "Configurations",
                {
                    c.name: "defined"
                    for c in Configuration.objects.filter(software_release__product=obj)
                },
            ),
            ("Product-level answers", _owned_answers(product=obj)),
            (
                "Baseline risk register",
                _risk_rows(e for e in RiskEntry.objects.filter(product=obj) if e.is_baseline),
            ),
        ]
    elif kind == "hardware_variant":
        subject = Subject(
            kind, f"{name} · {obj}", reverse("products:product_detail", args=[obj.product_id])
        )
        subject.sections = [
            (
                "Details",
                {
                    "Target markets": _markets(obj.target_markets),
                    "Approval": _approval(obj),
                },
            ),
            ("Revisions", {r.label: fmt(r.released_at) for r in obj.revisions.all()}),
        ]
    elif kind == "hardware_revision":
        subject = Subject(
            kind,
            f"{name} · {obj}",
            reverse("products:product_detail", args=[obj.hardware_variant.product_id]),
        )
        subject.sections = [
            (
                "Details",
                {
                    "Variant": obj.hardware_variant.name,
                    "Released": fmt(obj.released_at),
                    "Target markets": _markets(obj.hardware_variant.target_markets),
                    "Approval": _approval(obj),
                },
            ),
            ("Answers set here", _owned_answers(hardware_revision=obj)),
        ]
    elif kind == "software_release":
        subject = Subject(
            kind, f"{name} · {obj}", reverse("products:product_detail", args=[obj.product_id])
        )
        subject.sections = [
            (
                "Details",
                {
                    "Released": fmt(obj.released_at),
                    "Target markets": _markets(obj.target_markets),
                    "Approval": _approval(obj),
                },
            ),
            ("Options", {o.name: fmt(o.description) for o in obj.options.all()}),
            ("Answers set here", _owned_answers(software_release=obj)),
        ]
    elif kind == "software_option":
        subject = Subject(
            kind,
            f"{name} · {obj}",
            reverse("products:product_detail", args=[obj.software_release.product_id]),
        )
        subject.sections = [
            (
                "Details",
                {"Description": fmt(obj.description), "Approval": _approval(obj)},
            ),
            ("Answers set here", _owned_answers(software_option=obj)),
        ]
    elif kind == "configuration":
        subject = Subject(
            kind,
            f"{name} · {obj.name}",
            reverse("assessments:configuration_detail", args=[obj.pk]),
        )
        subject.sections = [
            (
                "Details",
                {
                    "Hardware revision": fmt(
                        str(obj.hardware_revision) if obj.hardware_revision_id else None
                    ),
                    "Software release": str(obj.software_release),
                    "Options": fmt([o.name for o in obj.software_options.all()]),
                    "Effective markets": fmt(obj.effective_market_codes()),
                    "Approval": _approval(obj),
                },
            ),
            *_evaluation_sections(evaluate_configuration(obj)),
            ("Risk register", _risk_rows(register_for_configuration(obj))),
        ]
    else:  # assessment
        evaluation = (
            obj.snapshot
            if obj.status == AssessmentStatus.APPROVED and obj.snapshot
            else evaluate_configuration(obj.configuration)
        )
        subject = Subject(
            kind,
            f"{name} · #{obj.pk} of {obj.configuration.name}",
            reverse("assessments:assessment_detail", args=[obj.pk]),
        )
        subject.sections = [
            (
                "Details",
                {
                    "Configuration": obj.configuration.name,
                    "Status": obj.get_status_display(),
                    "Approved": fmt(obj.approved_at.date() if obj.approved_at else None),
                    "Stale": fmt(obj.stale),
                    "Evaluated as of": fmt(evaluation.get("as_of")),
                },
            ),
            *_evaluation_sections(evaluation),
        ]
    return subject


def diff_subjects(a: Subject, b: Subject) -> list[SectionDiff]:
    titles = [t for t, _ in a.sections]
    titles += [t for t, _ in b.sections if t not in titles]
    a_sections, b_sections = dict(a.sections), dict(b.sections)
    diffs = []
    for title in titles:
        left, right = a_sections.get(title, {}), b_sections.get(title, {})
        rows = []
        for label in sorted(set(left) | set(right), key=str.lower):
            if label in left and label in right:
                status = SAME if left[label] == right[label] else CHANGED
            else:
                status = ONLY_A if label in left else ONLY_B
            rows.append(Row(label, left.get(label), right.get(label), status))
        if rows:
            diffs.append(SectionDiff(title, rows))
    return diffs


def visible_objects(user, kind: str):
    """Entities of ``kind`` under products ``user`` holds any role on."""
    model = KINDS[kind][1]
    lookup = _PRODUCT_LOOKUP[kind]
    products = editable_products(user, role=None)
    queryset = (
        model.objects.filter(pk__in=products)
        if not lookup
        else model.objects.filter(**{f"{lookup}__in": products})
    )
    return queryset.distinct()


def choice_label(kind: str, obj) -> str:
    if kind == "product":
        return f"{obj.product_family.name} / {obj.name}"
    if kind == "assessment":
        return f"#{obj.pk} · {obj.configuration.name} · {obj.get_status_display()}"
    prefix = product_of(obj).name
    return f"{prefix} · {obj}" if kind != "configuration" else f"{prefix} · {obj.name}"
