"""Evaluates a Configuration's active packages against its resolved answers.

Produces, per package: in/out of scope, matched classifications, the
requirements and assessment routes that apply, and any findings —
before a snapshot is ever taken (see docs/architecture.md, "Products and
assessments", "Findings" and "Results").
"""

from django.utils import timezone

from apps.evidence.models import EvidenceLink, EvidenceTargetType
from apps.packages.evaluator import evaluate_package

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


def evaluate_configuration(configuration, resolved=None, packages=None, *, as_of=None) -> dict:
    """``as_of`` is the assessment date that calendar-dated requirements
    are compared with (docs/adr/0019-requirement-applicability.md); today
    by default."""
    if resolved is None or packages is None:
        resolved, packages = resolve_answers(configuration)
    if as_of is None:
        as_of = timezone.localdate()

    data = {question_id: ra.value for question_id, ra in resolved.items()}

    results = []
    findings = []
    for package in packages:
        outcome = evaluate_package(package.content, data, as_of=as_of)
        findings.extend(
            {
                "id": rule["id"],
                "level": rule["level"],
                "message": rule["message"],
                "ref": rule.get("ref"),
                "source": package.source,
                "version": package.version,
            }
            for rule in outcome["findings"]
        )
        requirements = outcome["requirements"]
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
                "in_scope": outcome["in_scope"],
                "classifications": outcome["classifications"],
                "role": outcome["role"],
                "requirements": requirements,
                "upcoming_requirements": outcome["upcoming_requirements"],
                "ended_requirements": outcome["ended_requirements"],
                "assessment_routes": outcome["assessment_routes"],
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

    return {
        "as_of": as_of.isoformat(),
        "resolved_answers": resolved_answers,
        "results": results,
        "findings": findings,
    }
