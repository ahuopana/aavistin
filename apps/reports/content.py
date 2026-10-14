"""Report content: a plain JSON-able dict built from the selected sections.

The PDF is rendered from this dict only (ADR 0041), so the stored content
is exactly what was printed. Snapshot sections come from the frozen
snapshot when the report is approved, from live data for a draft.
"""

from apps.assessments.evaluation import evaluate_configuration
from apps.assessments.models import AssessmentStatus
from apps.evidence.models import Evidence
from apps.packages.models import RequirementPackage
from apps.risk.approval import build_snapshot
from apps.risk.models import RiskAssessmentStatus, RiskEntry

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
    """Question and requirement labels from the packages the evaluation used."""
    ids = [r.get("package_id") for r in evaluation["results"]]
    packages = list(RequirementPackage.objects.filter(pk__in=[i for i in ids if i]))
    questions, requirements = {}, {}
    for package in packages:
        for q in package.content.get("questions", []):
            questions.setdefault(q["id"], q.get("label") or q["id"])
        for r in package.content.get("requirements", []):
            requirements[(package.pk, r["id"])] = {
                "label": r.get("label") or r["id"],
                "ref": r.get("ref", ""),
            }
    titles = {p.pk: p.content.get("title") or p.source for p in packages}
    return questions, requirements, titles


def _assessment(evaluation, approved):
    questions, requirements, titles = _labels(evaluation)
    results = []
    for result in evaluation["results"]:
        pk = result.get("package_id")
        results.append(
            {
                "title": titles.get(pk, result["source"]),
                "source": result["source"],
                "version": result["version"],
                "in_scope": result["in_scope"],
                "classifications": result["classifications"],
                "assessment_routes": result["assessment_routes"],
                "requirements": [
                    requirements.get((pk, rid), {"label": rid, "ref": ""})
                    for rid in result["requirements"]
                ],
            }
        )
    answers = [
        {
            "question": questions.get(qid, qid),
            "value": a["value"],
            "needs_confirmation": a["needs_confirmation"],
        }
        for qid, a in sorted(evaluation["resolved_answers"].items())
    ]
    return {
        "frozen": approved,
        "as_of": evaluation["as_of"],
        "results": results,
        "findings": evaluation["findings"],
        "answers": answers,
    }


def _entry_labels(snapshot):
    return {e["id"]: e["label"] for e in snapshot["entries"]}


def _risks(snapshot):
    entries = RiskEntry.objects.filter(pk__in=[e["id"] for e in snapshot["entries"]])
    types = {e.pk: e.get_entry_type_display() for e in entries}
    return [
        {
            "type": types.get(e["id"], e["entry_type"]),
            "label": e["label"],
            "baseline": e["is_baseline"],
            "ratings": e.get("ratings") or e.get("asset_ratings") or [],
            "consistency_issues": e.get("consistency_issues", []),
        }
        for e in snapshot["entries"]
    ]


def _mitigations(snapshot):
    labels = _entry_labels(snapshot)
    controls = {c["id"]: c for c in snapshot["controls"]}
    return {
        "treatments": [
            {
                "entry": e["label"],
                "method": t["method"],
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


def _evidence(product):
    items = []
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
                "requirements": [k.requirement_id for k in ev.links.all() if k.requirement_id],
            }
        )
    return items


def build_content(configuration, sections, *, title, generated_by, generated_at, approved):
    """The report as a dict. ``approved`` selects frozen snapshots; otherwise live data."""
    product = configuration.product
    content = {
        "title": title,
        "status": "approved" if approved else "draft",
        "generated_at": generated_at.isoformat(),
        "generated_by": generated_by.get_full_name() or generated_by.get_username(),
        "configuration": configuration.name,
        "sections": [s for s in SECTION_KEYS if s in sections],
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
        content["assessment"] = _assessment(evaluation, bool(assessment))
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
        if "risks" in sections:
            content["risks"] = {
                "frozen": bool(risk),
                "entries": _risks(snapshot),
                "methods": snapshot["methods"],
                "catalogs": snapshot["catalogs"],
            }
        if "mitigations" in sections:
            content["mitigations"] = {"frozen": bool(risk), **_mitigations(snapshot)}
        if risk:
            content["sources"]["risk"] = {
                "id": risk.pk,
                "approved_at": risk.approved_at.isoformat(),
                "approved_by": _name(risk.approved_by),
            }
    if "evidence" in sections:
        content["evidence"] = _evidence(product)
    return content


def _name(user):
    return (user.get_full_name() or user.get_username()) if user else ""
