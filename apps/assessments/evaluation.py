"""Evaluates a Configuration's active packages against its resolved answers.

Produces, per package: in/out of scope, matched classifications, the
requirements and assessment routes that apply, and any findings —
before a snapshot is ever taken (see docs/architecture.md, "Products and
assessments", "Findings" and "Results").
"""

from apps.evidence.models import EvidenceLink, EvidenceTargetType
from apps.packages.fixtures_runner import evaluate_scope
from apps.packages.ruleengine import evaluate

from .resolution import resolve_answers


def _requirement_evidence_fingerprint(
    source: str, version: str, requirement_id: str
) -> list[dict]:
    """Which evidence currently backs a requirement, and whether each is
    still current -- feeds each result's `requirement_evidence`, frozen
    into Assessment.snapshot on approval like everything else `evaluate_
    configuration` returns, so `recompute_staleness` also picks up
    evidence that's expired or been superseded and never relinked (see
    docs/architecture.md, "Evidence", and apps.risk.approval's matching
    `_control_evidence_fingerprint`).
    """
    links = (
        EvidenceLink.objects.filter(
            target_type=EvidenceTargetType.REQUIREMENT,
            requirement_source=source,
            requirement_version=version,
            requirement_id=requirement_id,
        )
        .select_related("evidence")
        .order_by("evidence_id")
    )
    return [
        {
            "evidence_id": link.evidence_id,
            "current": not (link.evidence.is_superseded or link.evidence.is_expired),
        }
        for link in links
    ]


def evaluate_configuration(configuration, resolved=None, packages=None) -> dict:
    if resolved is None or packages is None:
        resolved, packages = resolve_answers(configuration)

    data = {question_id: ra.value for question_id, ra in resolved.items()}

    results = []
    findings = []
    for package in packages:
        content = package.content
        in_scope = evaluate_scope(content, data)

        classification_ids = []
        for classification in content.get("classifications", []):
            condition = classification.get("when")
            if condition is None or evaluate(condition, data):
                classification_ids.append(classification["id"])

        extended_data = {**data, **{f"class__{cid}": True for cid in classification_ids}}

        package_findings = []
        for rule in content.get("finding_rules", []):
            if evaluate(rule.get("when", False), extended_data):
                package_findings.append(
                    {
                        "id": rule["id"],
                        "level": rule["level"],
                        "message": rule["message"],
                        "ref": rule.get("ref"),
                        "source": package.source,
                        "version": package.version,
                    }
                )
        findings.extend(package_findings)

        requirements = []
        if in_scope:
            for requirement in content.get("requirements", []):
                applies_to = requirement.get("applies_to_classes")
                if not applies_to or set(applies_to) & set(classification_ids):
                    requirements.append(requirement["id"])

        routes = [
            route["id"]
            for route in content.get("assessment_routes", [])
            if evaluate(route.get("allowed_when", True), extended_data)
        ]

        requirement_evidence = {
            requirement_id: fingerprint
            for requirement_id in requirements
            if (
                fingerprint := _requirement_evidence_fingerprint(
                    package.source, package.version, requirement_id
                )
            )
        }

        results.append(
            {
                "source": package.source,
                "version": package.version,
                "package_id": package.pk,
                "package_type": package.package_type,
                "creates_legal_obligations": package.creates_legal_obligations,
                "in_scope": in_scope,
                "classifications": classification_ids,
                "requirements": requirements,
                "assessment_routes": routes,
                "requirement_evidence": requirement_evidence,
            }
        )

    resolved_answers = {
        question_id: {
            "value": ra.value,
            "needs_confirmation": ra.needs_confirmation,
            "origin": ra.origin,
        }
        for question_id, ra in resolved.items()
    }

    return {"resolved_answers": resolved_answers, "results": results, "findings": findings}
