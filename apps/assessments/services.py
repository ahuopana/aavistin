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
    return configuration.product.product_family


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


def sod_preview(assessment: Assessment, user, resolved=None) -> str | None:
    """What separation of duties would say if ``user`` approved now:
    ``None`` (no conflict or policy off), ``"warn"`` or ``"enforce"``."""
    if resolved is None:
        resolved, _packages = resolve_answers(assessment.configuration)
    if user.id not in _editors_of(resolved):
        return None
    policy = effective_sod_policy(product_family=_product_family(assessment.configuration))
    if policy in (SoDPolicy.WARN, SoDPolicy.ENFORCE):
        return policy
    return None


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


def _requirement_evidence_snapshot(results) -> dict:
    """(source, version) -> requirement_evidence, for the staleness diff
    below. Narrower than comparing `results` wholesale (which also
    carries in_scope/classifications/routes, already implied by
    resolved_answers and package-version changes) -- only the evidence
    fingerprint apps.evidence needs to detect expiry or supersession.
    """
    return {(r["source"], r["version"]): r.get("requirement_evidence", {}) for r in results}


def _in_force_requirements(results) -> dict:
    """(source, version) -> requirements in force. Calendar-dated
    requirements change with the assessment date alone, so a passing date
    must flag an approved assessment (docs/adr/0019-requirement-applicability.md)."""
    return {(r["source"], r["version"]): sorted(r.get("requirements", [])) for r in results}


def staleness_report(assessment: Assessment, current=None) -> dict:
    """What differs between an approved assessment's snapshot and the
    current evaluation: the same four checks that make it stale, itemised
    so the assessment page can say why.

    ``{"answers": [{"id", "before", "after"}], "packages": [{"source",
    "before", "after"}], "evidence": [{"source", "version",
    "requirement_id"}], "requirements": [{"source", "version", "entered",
    "left"}], "any": bool}``. ``before``/``after`` are None for an answer or
    package that is new or gone.
    """
    snapshot = assessment.snapshot or {}
    if current is None:
        current = evaluate_configuration(assessment.configuration)

    then_answers = snapshot.get("resolved_answers", {})
    now_answers = current["resolved_answers"]
    answers = [
        {
            "id": qid,
            "before": (then_answers.get(qid) or {}).get("value"),
            "after": (now_answers.get(qid) or {}).get("value"),
        }
        for qid in sorted(set(then_answers) | set(now_answers))
        if then_answers.get(qid) != now_answers.get(qid)
    ]

    then_packages = {(p["source"], p["version"]) for p in snapshot.get("packages", [])}
    now_packages = {(r["source"], r["version"]) for r in current["results"]}
    sources = sorted({s for s, _ in then_packages ^ now_packages})
    packages = [
        {
            "source": source,
            "before": next(
                (v for s, v in sorted(then_packages - now_packages) if s == source), None
            ),
            "after": next(
                (v for s, v in sorted(now_packages - then_packages) if s == source), None
            ),
        }
        for source in sources
    ]

    then_evidence = _requirement_evidence_snapshot(snapshot.get("results", []))
    now_evidence = _requirement_evidence_snapshot(current["results"])
    evidence = [
        {"source": key[0], "version": key[1], "requirement_id": requirement_id}
        for key in sorted(set(then_evidence) | set(now_evidence))
        for requirement_id in sorted(
            set(then_evidence.get(key, {})) | set(now_evidence.get(key, {}))
        )
        if then_evidence.get(key, {}).get(requirement_id)
        != now_evidence.get(key, {}).get(requirement_id)
    ]

    then_in_force = _in_force_requirements(snapshot.get("results", []))
    now_in_force = _in_force_requirements(current["results"])
    requirements = []
    # Requirements also move with answers and packages; listed on their own
    # only when neither changed, i.e. a date brought them into or out of force.
    for key in sorted(set(then_in_force) & set(now_in_force)) if not (answers or packages) else []:
        before, after = set(then_in_force[key]), set(now_in_force[key])
        if before != after:
            requirements.append(
                {
                    "source": key[0],
                    "version": key[1],
                    "entered": sorted(after - before),
                    "left": sorted(before - after),
                }
            )
    # A package whose version changed is reported under packages; its
    # requirements and evidence differ by definition.
    changed = {(p["source"]) for p in packages}
    evidence = [e for e in evidence if e["source"] not in changed]
    any_change = bool(answers or packages or evidence or requirements) or (
        then_in_force != now_in_force
    )
    return {
        "answers": answers,
        "packages": packages,
        "evidence": evidence,
        "requirements": requirements,
        "any": any_change,
    }


def staleness_summary(report: dict) -> str:
    """One line for the stale warning and the workflow chip, e.g.
    "3 answers, 1 package version, evidence for 1 requirement"."""
    parts = []
    if report["answers"]:
        n = len(report["answers"])
        parts.append(f"{n} answer{'s' if n != 1 else ''}")
    if report["packages"]:
        n = len(report["packages"])
        parts.append(f"{n} package version{'s' if n != 1 else ''}")
    if report["evidence"]:
        n = len(report["evidence"])
        parts.append(f"evidence for {n} requirement{'s' if n != 1 else ''}")
    if report["requirements"]:
        n = sum(len(r["entered"]) + len(r["left"]) for r in report["requirements"])
        parts.append(f"{n} requirement{'s' if n != 1 else ''} in or out of force by date")
    return ", ".join(parts)


def recompute_staleness(assessment: Assessment) -> bool:
    """Recomputes and persists Assessment.stale; returns the new value.

    Called explicitly — by `recompute_all_staleness` below (itself called
    from the `refresh_assessment_staleness` management command and from
    `apps.assessments.tasks.refresh_staleness_task`, see
    docs/adr/0007-background-job-backend.md) — never from a signal, so a
    single answer edit doesn't trigger a recompute storm across every
    assessment that might reference it.
    """
    if assessment.status != AssessmentStatus.APPROVED or assessment.snapshot is None:
        return False

    is_stale = staleness_report(assessment)["any"]
    if is_stale != assessment.stale:
        assessment.stale = is_stale
        assessment.save(update_fields=["stale"])
    return is_stale


def recompute_all_staleness() -> tuple[int, int]:
    """Recomputes staleness for every approved assessment.

    Returns (checked, newly_stale). Shared by the manual management
    command and the periodic task so there's one code path either way.
    """
    checked = 0
    newly_stale = 0
    for assessment in Assessment.objects.filter(status=AssessmentStatus.APPROVED):
        checked += 1
        if recompute_staleness(assessment):
            newly_stale += 1
    return checked, newly_stale
