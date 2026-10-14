"""Report content: a plain JSON-able dict built from the selected sections.

The PDF is rendered from this dict only (ADR 0041), so the stored content
is exactly what was printed. Snapshot sections come from the frozen
snapshot when the report is approved, from live data for a draft.
"""

from apps.assessments.evaluation import evaluate_configuration
from apps.assessments.findings import finding_details
from apps.assessments.models import AssessmentStatus
from apps.assessments.templatetags.assessment_tags import choice_label
from apps.core.compare import display, question_labels
from apps.core.version import aavistin_version
from apps.evidence.models import Evidence
from apps.orgs.models import Role
from apps.orgs.services import roles_for_user
from apps.packages.models import PackageStatus, RequirementPackage
from apps.risk.approval import build_snapshot
from apps.risk.models import RiskAssessmentStatus, RiskEntry

from .summary import build_summary

SECTIONS = [
    ("product", "Product"),
    ("hardware", "Hardware"),
    ("software", "Software"),
    ("options", "Software options"),
    ("assessment", "Assessment"),
    ("risks", "Risks"),
    ("mitigations", "Mitigations"),
    ("evidence", "Evidence"),
]
SECTION_KEYS = [key for key, _ in SECTIONS]
LEVEL_LABELS = {"action_required": "Action required", "caution": "Caution", "info": "Info"}
ROLE_ORDER = [Role.ORG_ADMIN, Role.APPROVER, Role.EDITOR, Role.CONTENT_CURATOR, Role.VIEWER]
SNAPSHOT_SECTIONS = {"assessment": "assessment", "risks": "risk", "mitigations": "risk"}


def latest_approved_assessment(configuration):
    return (
        configuration.assessments.filter(status=AssessmentStatus.APPROVED)
        .order_by("-approved_at")
        .first()
    )


def latest_approved_risk_assessment(configuration):
    return (
        configuration.risk_assessments.filter(status=RiskAssessmentStatus.APPROVED)
        .order_by("-approved_at")
        .first()
    )


def issue_blockers(configuration, sections) -> list[str]:
    """Why an approved report cannot be issued for these sections (empty: it can)."""
    wanted = {SNAPSHOT_SECTIONS[s] for s in sections if s in SNAPSHOT_SECTIONS}
    if not wanted:
        return [
            "Select the assessment, risks or mitigations: only they have an approved snapshot."
        ]
    blockers = []
    if "assessment" in wanted:
        assessment = latest_approved_assessment(configuration)
        if assessment is None:
            blockers.append("The assessment is not approved.")
        elif assessment.stale:
            blockers.append("The approved assessment is stale; review and approve it again.")
    if "risk" in wanted:
        risk = latest_approved_risk_assessment(configuration)
        if risk is None:
            blockers.append("The risk register is not approved.")
        elif risk.stale:
            blockers.append("The approved risk register is stale; review and approve it again.")
    return blockers


def _markets(entity):
    return sorted(entity.target_markets.values_list("name", flat=True))


def _product(product):
    family = product.product_family
    return {
        "name": product.name,
        "description": product.description,
        "status": product.get_status_display(),
        "family": family.name,
        "organisation": family.organisation.name,
    }


def _hardware(configuration):
    revision = configuration.hardware_revision
    if revision is None:
        return None
    variant = revision.hardware_variant
    return {
        "variant": variant.name,
        "revision": revision.label,
        "released_at": revision.released_at.isoformat() if revision.released_at else "",
        "target_markets": _markets(variant),
    }


def _software(configuration):
    release = configuration.software_release
    return {
        "name": release.name,
        "version": release.version,
        "released_at": release.released_at.isoformat() if release.released_at else "",
        "target_markets": _markets(release),
    }


def _options(configuration):
    return [
        {"name": o.name, "description": o.description}
        for o in configuration.software_options.order_by("name")
    ]


def _labels(evaluation):
    """Labels from the packages the evaluation used: questions, requirements,
    classifications, assessment routes and package titles."""
    ids = [r.get("package_id") for r in evaluation["results"]]
    packages = list(RequirementPackage.objects.filter(pk__in=[i for i in ids if i]))
    labels = {"questions": {}, "requirements": {}, "classes": {}, "routes": {}, "titles": {}}
    for package in packages:
        content = package.content
        for q in content.get("questions", []):
            labels["questions"].setdefault(q["id"], q.get("label") or q["id"])
        for r in content.get("requirements", []):
            labels["requirements"][(package.pk, r["id"])] = {
                "label": r.get("label") or r["id"],
                "ref": r.get("ref", ""),
            }
        for c in content.get("classifications", []):
            labels["classes"][(package.pk, c["id"])] = c.get("label") or choice_label(c["id"])
        for route in content.get("assessment_routes", []):
            labels["routes"][(package.pk, route["id"])] = route.get("label") or choice_label(
                route["id"]
            )
        labels["titles"][package.pk] = content.get("title") or package.source
    # Shared questions (e.g. package "common") belong to no result package.
    for qid, label in question_labels().items():
        labels["questions"].setdefault(qid, label)
    return labels


def _package_titles() -> dict[str, str]:
    """Source id -> title, for methods and catalogs ("default-cia-5x5" -> its title)."""
    titles = {}
    for package in RequirementPackage.objects.filter(status=PackageStatus.APPROVED).order_by(
        "version"
    ):
        titles[package.source] = package.content.get("title") or package.source
    return titles


def _answer_text(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value is None or value == "":
        return "Not answered"
    shown = display(value)
    if isinstance(shown, list):
        return ", ".join(str(v) for v in shown)
    return str(shown)


def _assessment(evaluation, approved, *, include_out_of_scope):
    labels = _labels(evaluation)
    questions = {qid: {"label": label} for qid, label in labels["questions"].items()}
    results = []
    out_of_scope = 0
    for result in evaluation["results"]:
        pk = result.get("package_id")
        if not result["in_scope"]:
            out_of_scope += 1
            if not include_out_of_scope:
                continue
        results.append(
            {
                "title": labels["titles"].get(pk, result["source"]),
                "source": result["source"],
                "version": result["version"],
                "in_scope": result["in_scope"],
                "classifications": [
                    labels["classes"].get((pk, cid), choice_label(cid))
                    for cid in result["classifications"]
                ],
                "assessment_routes": [
                    labels["routes"].get((pk, rid), choice_label(rid))
                    for rid in result["assessment_routes"]
                ],
                "requirements": [
                    labels["requirements"].get((pk, rid), {"label": rid, "ref": ""})
                    for rid in result["requirements"]
                ],
            }
        )
    titles = {(r["source"], r["version"]): r["title"] for r in results}
    for r in evaluation["results"]:
        titles.setdefault((r["source"], r["version"]), labels["titles"].get(r.get("package_id")))
    findings = [
        {
            "level": LEVEL_LABELS.get(f["level"], f["level"]),
            "level_id": f["level"],
            "message": f["message"],
            "ref": f.get("ref") or "",
            "package": titles.get((f["source"], f["version"])) or f["source"],
            "out_of_scope": f["out_of_scope"],
        }
        for f in finding_details(
            evaluation["findings"],
            evaluation["resolved_answers"],
            questions,
            evaluation["results"],
        )
    ]
    answers = [
        {
            "question": labels["questions"].get(qid, qid),
            "value": _answer_text(a["value"]),
            "needs_confirmation": a["needs_confirmation"],
        }
        for qid, a in sorted(evaluation["resolved_answers"].items())
    ]
    return {
        "frozen": approved,
        "as_of": evaluation["as_of"],
        "results": results,
        "out_of_scope_count": out_of_scope,
        "include_out_of_scope": include_out_of_scope,
        "findings": findings,
        "answers": answers,
    }


def _entry_labels(snapshot):
    return {e["id"]: e["label"] for e in snapshot["entries"]}


def _risks(snapshot, titles):
    entries = RiskEntry.objects.filter(pk__in=[e["id"] for e in snapshot["entries"]])
    types = {e.pk: e.get_entry_type_display() for e in entries}
    return [
        {
            "type": types.get(e["id"], e["entry_type"]),
            "label": e["label"],
            "baseline": e["is_baseline"],
            "ratings": [
                {**r, "method": titles.get(r["method"], r["method"])}
                for r in e.get("ratings") or e.get("asset_ratings") or []
            ],
            "consistency_issues": e.get("consistency_issues", []),
        }
        for e in snapshot["entries"]
    ]


def _mitigations(snapshot, titles):
    labels = _entry_labels(snapshot)
    controls = {c["id"]: c for c in snapshot["controls"]}
    return {
        "treatments": [
            {
                "entry": e["label"],
                "method": titles.get(t["method"], t["method"]),
                "treatment": t["treatment_type"],
                "residual": t["residual"],
            }
            for e in snapshot["entries"]
            for t in e.get("treatments", [])
        ],
        "controls": [
            {
                "name": c["name"],
                "status": c["status"],
                "threats": [labels.get(i, str(i)) for i in c["threats"]],
                "evidence_count": len(c["evidence"]),
                "evidence_current": all(ev["current"] for ev in c["evidence"]),
            }
            for c in controls.values()
        ],
    }


def _requirement_label(cache, source, version, requirement_id):
    key = (source, version)
    if key not in cache:
        package = RequirementPackage.objects.filter(source=source, version=version).first()
        cache[key] = {
            r["id"]: r.get("label") or r["id"]
            for r in (package.content.get("requirements", []) if package else [])
        }
    return cache[key].get(requirement_id, requirement_id)


def _evidence(product):
    items = []
    cache = {}
    for ev in (
        Evidence.objects.filter(product=product)
        .prefetch_related("links__control")
        .order_by("title")
    ):
        items.append(
            {
                "title": ev.title,
                "kind": ev.get_kind_display(),
                "sha256": ev.file.checksum if ev.file_id else "",
                "valid_until": ev.valid_until.isoformat() if ev.valid_until else "",
                "last_audit_date": ev.last_audit_date.isoformat() if ev.last_audit_date else "",
                "expired": ev.is_expired,
                "superseded": ev.is_superseded,
                "controls": [k.control.name for k in ev.links.all() if k.control_id],
                "requirements": [
                    _requirement_label(
                        cache, k.requirement_source, k.requirement_version, k.requirement_id
                    )
                    for k in ev.links.all()
                    if k.requirement_id
                ],
            }
        )
    return items


def document_type(sections) -> str:
    """What the document is, from what it contains."""
    assessed, risked = "assessment" in sections, bool({"risks", "mitigations"} & set(sections))
    if assessed and risked:
        return "Product Compliance and Risk Assessment Report"
    if assessed:
        return "Product Compliance Assessment Report"
    if risked:
        return "Product Risk Assessment Report"
    return "Product Report"


def generator_label(user, product) -> str:
    """ "Firstname Lastname, Approver": the person's highest role on the product
    (the user model has no job title)."""
    name = _name(user)
    if user.is_superuser:
        return f"{name}, Administrator"
    roles = roles_for_user(user, product=product)
    for role in ROLE_ORDER:
        if role in roles:
            return f"{name}, {Role(role).label}"
    return name


def build_content(
    configuration,
    sections,
    *,
    title,
    generated_by,
    generated_at,
    approved,
    include_out_of_scope=False,
):
    """The report as a dict. ``approved`` selects frozen snapshots; otherwise live data."""
    product = configuration.product
    content = {
        "title": title,
        "document_type": document_type(sections),
        "status": "approved" if approved else "draft",
        "generated_at": generated_at.isoformat(),
        "generated_by": generator_label(generated_by, product),
        "aavistin_version": aavistin_version(),
        "configuration": configuration.name,
        "sections": [s for s in SECTION_KEYS if s in sections],
        "section_labels": [label for key, label in SECTIONS if key in sections],
        "sources": {},
    }
    if "product" in sections:
        content["product"] = _product(product)
    if "hardware" in sections:
        content["hardware"] = _hardware(configuration)
    if "software" in sections:
        content["software"] = _software(configuration)
    if "options" in sections:
        content["options"] = _options(configuration)

    if "assessment" in sections:
        assessment = latest_approved_assessment(configuration) if approved else None
        evaluation = assessment.snapshot if assessment else evaluate_configuration(configuration)
        content["assessment"] = _assessment(
            evaluation, bool(assessment), include_out_of_scope=include_out_of_scope
        )
        if assessment:
            content["sources"]["assessment"] = {
                "id": assessment.pk,
                "approved_at": assessment.approved_at.isoformat(),
                "approved_by": _name(assessment.approved_by),
                "sod_warning": assessment.sod_warning,
            }
    if "risks" in sections or "mitigations" in sections:
        risk = latest_approved_risk_assessment(configuration) if approved else None
        snapshot = risk.snapshot if risk else build_snapshot(configuration)
        titles = _package_titles()
        if "risks" in sections:
            content["risks"] = {
                "frozen": bool(risk),
                "entries": _risks(snapshot, titles),
                "methods": [
                    {"title": titles.get(source, source), "version": version}
                    for source, version in snapshot["methods"]
                ],
                "catalogs": [
                    {"title": titles.get(source, source), "version": version}
                    for source, version in snapshot["catalogs"]
                ],
            }
        if "mitigations" in sections:
            content["mitigations"] = {"frozen": bool(risk), **_mitigations(snapshot, titles)}
        if risk:
            content["sources"]["risk"] = {
                "id": risk.pk,
                "approved_at": risk.approved_at.isoformat(),
                "approved_by": _name(risk.approved_by),
            }
    if "evidence" in sections:
        content["evidence"] = _evidence(product)
    content["summary"] = build_summary(content)
    return content


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""
