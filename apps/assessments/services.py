"""Approval (with separation-of-duties enforcement) and stale detection.

See docs/architecture.md, "Organisations and roles" (separation of
duties) and "Products and assessments" ("Snapshots").
"""

from django.utils import timezone

from apps.orgs.models import SoDPolicy
from apps.orgs.services import effective_sod_policy

from .evaluation import evaluate_configuration
from .models import Assessment, AssessmentStatus
from .resolution import resolve_answers


class AssessmentError(Exception):
    pass


class SoDViolation(AssessmentError):
    pass


def _product_family(configuration):
    return configuration.hardware_revision.hardware_variant.product.product_family


def _editors_of(resolved) -> set[int]:
    """Everyone who ever edited any answer feeding this snapshot — not
    just its current value's author (see docs/architecture.md: "'Same
    person' means anyone who edited any answer in the snapshot, not just
    the last editor")."""
    editor_ids: set[int] = set()
    for resolved_answer in resolved.values():
        answer = resolved_answer.answer
        if answer is None:
            continue
        if answer.created_by_id:
            editor_ids.add(answer.created_by_id)
        editor_ids.update(answer.history.all().values_list("history_user_id", flat=True))
    editor_ids.discard(None)
    return editor_ids


def approve_assessment(assessment: Assessment, *, actor) -> Assessment:
    if assessment.status == AssessmentStatus.APPROVED:
        raise AssessmentError("assessment is already approved")

    resolved, packages = resolve_answers(assessment.configuration)
    evaluation = evaluate_configuration(assessment.configuration, resolved, packages)

    policy = effective_sod_policy(product_family=_product_family(assessment.configuration))
    editors = _editors_of(resolved)

    sod_warning = False
    if actor is not None and actor.id in editors:
        if policy == SoDPolicy.ENFORCE:
            raise SoDViolation(
                "separation of duties: you edited an answer feeding this assessment, "
                "and the organisation's policy is 'enforce'; another approver is required"
            )
        if policy == SoDPolicy.WARN:
            sod_warning = True

    assessment.snapshot = {
        **evaluation,
        "packages": [
            {"source": r["source"], "version": r["version"], "package_id": r["package_id"]}
            for r in evaluation["results"]
        ],
        "sod_warning": sod_warning,
    }
    assessment.status = AssessmentStatus.APPROVED
    assessment.approved_at = timezone.now()
    assessment.approved_by = actor
    assessment.sod_warning = sod_warning
    assessment.stale = False
    assessment.save()
    return assessment


def recompute_staleness(assessment: Assessment) -> bool:
    """Recomputes and persists Assessment.stale; returns the new value.

    Not wired to fire automatically on every relevant change (that's
    background-job territory, and docs/architecture.md leaves the
    background job backend as an open question) — call this explicitly,
    e.g. from the `refresh_assessment_staleness` management command.
    """
    if assessment.status != AssessmentStatus.APPROVED or assessment.snapshot is None:
        return False

    current = evaluate_configuration(assessment.configuration)
    current_packages = {(r["source"], r["version"]) for r in current["results"]}
    snapshot_packages = {
        (p["source"], p["version"]) for p in assessment.snapshot.get("packages", [])
    }

    is_stale = (
        current["resolved_answers"] != assessment.snapshot.get("resolved_answers", {})
        or current_packages != snapshot_packages
    )
    if is_stale != assessment.stale:
        assessment.stale = is_stale
        assessment.save(update_fields=["stale"])
    return is_stale
