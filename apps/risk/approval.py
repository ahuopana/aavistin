"""Approval snapshot and stale detection for a configuration's risk view.

Mirrors apps.assessments.services: freezes the resolved register
(baseline + deltas), ratings, treatments and method/catalog versions;
later changes never alter an approved snapshot, only flag it stale (see
docs/architecture.md, "Treatment and approval").
"""

from django.utils import timezone

from .consistency import check_threat_hazard_consistency
from .models import EntryType, RiskAssessment, RiskAssessmentStatus
from .rating import evaluate_entry_rating, evaluate_residual_rating
from .resolution import register_for_configuration


class RiskAssessmentError(Exception):
    pass


def build_snapshot(configuration) -> dict:
    entries = register_for_configuration(configuration)
    entries_data = []
    methods_used: set[tuple[str, str]] = set()
    catalogs_used: set[tuple[str, str]] = set()

    for entry in entries:
        entry_data = {
            "id": entry.id,
            "entry_type": entry.entry_type,
            "label": entry.label,
            "is_baseline": entry.is_baseline,
            "suggestion_status": entry.suggestion_status,
        }
        if entry.source_catalog_id:
            catalogs_used.add((entry.source_catalog.source, entry.source_catalog.version))

        if entry.entry_type == EntryType.ASSET:
            entry_data["asset_ratings"] = [
                {"method": r.method.source, "property": r.property, "severity": r.severity}
                for r in entry.asset_ratings.all()
            ]
            methods_used.update(
                (r.method.source, r.method.version) for r in entry.asset_ratings.all()
            )
        else:
            rated_methods = {r.method for r in entry.ratings.all()}
            entry_data["ratings"] = [
                {"method": method.source, **evaluate_entry_rating(entry, method)}
                for method in rated_methods
            ]
            methods_used.update((m.source, m.version) for m in rated_methods)
            entry_data["treatments"] = [
                {
                    "method": t.method.source,
                    "treatment_type": t.treatment_type,
                    "residual": evaluate_residual_rating(t),
                }
                for t in entry.treatments.all()
            ]
            if entry.entry_type == EntryType.THREAT:
                entry_data["consistency_issues"] = check_threat_hazard_consistency(entry)

        entries_data.append(entry_data)

    return {
        # Lists, not tuples: JSONField round-trips through the DB as
        # lists, so building tuples here would make a freshly-built
        # snapshot compare unequal to one just loaded from the database.
        "entries": entries_data,
        "methods": [list(m) for m in sorted(methods_used)],
        "catalogs": [list(c) for c in sorted(catalogs_used)],
    }


def approve_risk_assessment(risk_assessment, *, actor=None):
    if risk_assessment.status == RiskAssessmentStatus.APPROVED:
        raise RiskAssessmentError("risk assessment is already approved")

    risk_assessment.snapshot = build_snapshot(risk_assessment.configuration)
    risk_assessment.status = RiskAssessmentStatus.APPROVED
    risk_assessment.approved_at = timezone.now()
    risk_assessment.approved_by = actor
    risk_assessment.stale = False
    risk_assessment.save()
    return risk_assessment


def recompute_staleness(risk_assessment) -> bool:
    """Recomputes and persists RiskAssessment.stale; returns the new value.

    Called explicitly — by `recompute_all_staleness` below (itself called
    from the `refresh_risk_assessment_staleness` management command and
    from `apps.risk.tasks.refresh_staleness_task`, see
    docs/adr/0007-background-job-backend.md) — never from a signal.
    """
    if risk_assessment.status != RiskAssessmentStatus.APPROVED or risk_assessment.snapshot is None:
        return False

    is_stale = build_snapshot(risk_assessment.configuration) != risk_assessment.snapshot
    if is_stale != risk_assessment.stale:
        risk_assessment.stale = is_stale
        risk_assessment.save(update_fields=["stale"])
    return is_stale


def recompute_all_staleness() -> tuple[int, int]:
    """Recomputes staleness for every approved risk assessment.

    Returns (checked, newly_stale). Shared by the manual management
    command and the periodic task so there's one code path either way.
    """
    checked = 0
    newly_stale = 0
    for risk_assessment in RiskAssessment.objects.filter(status=RiskAssessmentStatus.APPROVED):
        checked += 1
        if recompute_staleness(risk_assessment):
            newly_stale += 1
    return checked, newly_stale
