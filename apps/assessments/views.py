from datetime import date

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.core.navigation import breadcrumbs, configuration_workflow
from apps.core.readiness import assessment_readiness
from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.packages.models import PackageKind, RequirementPackage
from apps.products.models import Configuration

from .evaluation import evaluate_configuration
from .models import Answer, Assessment, AssessmentStatus
from .progress import is_open, questionnaire_progress
from .resolution import resolve_answers
from .services import (
    AssessmentError,
    SoDViolation,
    approve_assessment,
    sod_preview,
    staleness_report,
    staleness_summary,
)

LEVEL_TO_OWNER_FIELD = {
    "product": "product",
    "hardware": "hardware_revision",
    "software": "software_release",
    "option": "software_option",
}

LEVEL_LABELS = {
    "product": "Product",
    "hardware": "Hardware",
    "software": "Software",
    "option": "Option",
}


def _owners(configuration) -> dict:
    """Answer owner field -> the entities of ``configuration`` an answer at
    that level may be attached to (several only for options)."""
    product = configuration.product
    return {
        "product": [product],
        "hardware_revision": (
            [configuration.hardware_revision] if configuration.hardware_revision_id else []
        ),
        "software_release": [configuration.software_release],
        "software_option": list(configuration.software_options.order_by("id")),
    }


def _owner_label(level: str, owner) -> str:
    if level == "product":
        return f"Product · {owner.name}"
    if level == "hardware":
        return f"Hardware · {owner.hardware_variant.name} rev {owner.label}"
    if level == "software":
        return f"Software · {owner.name} {owner.version}"
    return f"Option · {owner.name}"


def _product(configuration):
    """Roles are checked at product scope, which also inherits family and
    organisation grants (apps.orgs.services.roles_for_user)."""
    return configuration.product


def _coerce_value(raw: str, question_type: str = ""):
    if raw == "":
        return raw
    if question_type == "boolean":
        return raw in ("true", "True")
    if question_type == "number":
        try:
            return float(raw) if "." in raw else int(raw)
        except ValueError:
            return raw
    if question_type == "choice":
        return raw
    if question_type == "date":
        # Stored as an ISO string (ADR 0018); the date input already sends one.
        try:
            return date.fromisoformat(raw).isoformat()
        except ValueError:
            return None
    # No (or unrecognised) declared type: best-effort guess, kept for
    # backward compatibility with callers that don't send question_type.
    if raw in ("true", "True"):
        return True
    if raw in ("false", "False"):
        return False
    try:
        return float(raw) if "." in raw else int(raw)
    except ValueError:
        return raw


def _display_order(item):
    """Sort key for ``(question_id, ResolvedAnswer)``: grouped questions in
    their package order, then ungrouped ones by id."""
    group = item[1].question.get("group")
    return (0, group["order"], "") if group else (1, 0, item[0])


def _next_open_question(configuration, saved_question_id: str) -> str:
    """The first unanswered question after the one just saved (wrapping to the
    start), or the saved question itself when nothing is left open."""
    resolved, _packages = resolve_answers(configuration)
    ordered = [qid for qid, _ in sorted(resolved.items(), key=_display_order)]
    start = ordered.index(saved_question_id) + 1 if saved_question_id in ordered else 0
    for qid in ordered[start:] + ordered[:start]:
        if qid != saved_question_id and resolved[qid].value is None:
            return qid
    return saved_question_id


@login_required
def configuration_detail(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = _product(configuration)
    resolved, packages = resolve_answers(configuration)

    product = configuration.product
    owners = _owners(configuration)

    any_grouped = any(r.question.get("group") for r in resolved.values())
    rows = []
    previous_group = object()
    for _question_id, resolved_answer in sorted(resolved.items(), key=_display_order):
        group = resolved_answer.question.get("group")
        group_start = any_grouped and (group["id"] if group else None) != previous_group
        previous_group = group["id"] if group else None
        level = resolved_answer.question.get("level")
        owner_type = LEVEL_TO_OWNER_FIELD.get(level)
        candidates = owners.get(owner_type, [])
        answer = resolved_answer.answer
        # The entity this answer is (or would be) stored on: the one already
        # holding it, else the first candidate (options: the editor may pick).
        owner = next(
            (c for c in candidates if answer and getattr(answer, f"{owner_type}_id") == c.pk),
            candidates[0] if candidates else None,
        )
        rows.append(
            {
                "question": resolved_answer.question,
                "group": group,
                "group_start": group_start,
                "value": resolved_answer.value,
                "justification": (
                    resolved_answer.answer.override_justification if resolved_answer.answer else ""
                ),
                "origin": resolved_answer.origin,
                "needs_confirmation": resolved_answer.needs_confirmation,
                "is_open": is_open(resolved_answer),
                "owner_type": owner_type,
                "owner_id": owner.pk if owner else None,
                "owner_choices": candidates if level == "option" and len(candidates) > 1 else [],
                "level": level,
                "owner_label": _owner_label(level, owner)
                if owner
                else LEVEL_LABELS.get(level, ""),
            }
        )
    # A group header stays visible under the "only open" filter while any
    # of its questions is still open.
    open_groups = {r["group"]["id"] if r["group"] else None for r in rows if r["is_open"]}
    group_levels: dict = {}
    group_open_levels: dict = {}
    for row in rows:
        key = row["group"]["id"] if row["group"] else None
        group_levels.setdefault(key, set()).add(row["level"])
        if row["is_open"]:
            group_open_levels.setdefault(key, set()).add(row["level"])
    for row in rows:
        key = row["group"]["id"] if row["group"] else None
        row["group_has_open"] = key in open_groups
        row["group_levels"] = sorted(group_levels.get(key, ()))
        row["group_open_levels"] = sorted(group_open_levels.get(key, ()))
    level_counts = [
        {
            "level": level,
            "label": label,
            "total": sum(1 for r in rows if r["level"] == level),
            "open": sum(1 for r in rows if r["level"] == level and r["is_open"]),
        }
        for level, label in LEVEL_LABELS.items()
    ]
    progress = questionnaire_progress(configuration, resolved)

    return render(
        request,
        "assessments/configuration_detail.html",
        {
            "configuration": configuration,
            "product": product,
            "rows": rows,
            "progress": progress,
            "level_counts": [c for c in level_counts if c["total"]],
            "level_filter": request.GET.get("level", ""),
            "crumbs": breadcrumbs(configuration=configuration),
            "workflow": configuration_workflow(configuration, request.user, progress=progress),
            "packages": [p for p in packages if p.kind == PackageKind.REQUIREMENT],
            "assessments": configuration.assessments.all(),
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
            "justification_help": Answer._meta.get_field("override_justification").help_text,
        },
    )


@login_required
@require_POST
def answer_question(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = _product(configuration)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to answer questions.")
        return redirect("assessments:configuration_detail", pk=pk)

    question_id = request.POST["question_id"]
    owner_type = request.POST["owner_type"]
    owner_id = request.POST.get("owner_id")
    if owner_type not in LEVEL_TO_OWNER_FIELD.values() or not owner_id:
        django_messages.error(request, "No entity to attach this answer to.")
        return redirect("assessments:configuration_detail", pk=pk)
    try:
        owner_id = int(owner_id)
    except ValueError:
        django_messages.error(request, "Invalid entity id.")
        return redirect("assessments:configuration_detail", pk=pk)

    # owner_type is already an Answer owner field name (product,
    # hardware_revision, software_release, software_option) — the
    # template renders it from LEVEL_TO_OWNER_FIELD in configuration_detail.
    # The owner must belong to this configuration.
    owner = next((o for o in _owners(configuration)[owner_type] if o.pk == owner_id), None)
    if owner is None:
        django_messages.error(request, "That entity is not part of this configuration.")
        return redirect("assessments:configuration_detail", pk=pk)
    owner_field = f"{owner_type}_id"
    question_type = request.POST.get("question_type", "")
    value = _coerce_value(request.POST.get("value", ""), question_type)
    if question_type == "date" and value is None:
        django_messages.error(request, "Enter the date as YYYY-MM-DD.")
        return redirect("assessments:configuration_detail", pk=pk)
    justification = request.POST.get("justification", "")

    try:
        answer = Answer.objects.get(question_id=question_id, **{owner_field: owner_id})
    except Answer.DoesNotExist:
        answer = Answer(question_id=question_id, **{owner_field: owner_id})

    answer.value = value
    answer.override_justification = justification
    if answer.created_by_id is None:
        answer.created_by = request.user
    answer._history_user = request.user

    try:
        answer.full_clean()
    except ValidationError as exc:
        for messages in exc.message_dict.values():
            for message in messages:
                django_messages.error(request, message)
        return redirect("assessments:configuration_detail", pk=pk)

    answer.save()
    level = next(k for k, v in LEVEL_TO_OWNER_FIELD.items() if v == owner_type)
    django_messages.success(
        request,
        f"Answer saved on {_owner_label(level, owner)}. It applies to every configuration "
        "that uses it.",
    )
    next_question = _next_open_question(configuration, question_id)
    return redirect(
        reverse("assessments:configuration_detail", args=[pk])
        + _filter_query(request.POST.get("return_query", ""))
        + f"#q-{next_question}"
    )


def _filter_query(raw: str) -> str:
    """Keep the questionnaire's own filters (``show``, ``level``) across a save."""
    params = QueryDict(raw)
    kept = {k: params[k] for k in ("show", "level") if params.get(k)}
    return "?" + urlencode(kept) if kept else ""


@login_required
@require_POST
def assessment_create(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = _product(configuration)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to start an assessment.")
        return redirect("assessments:configuration_detail", pk=pk)
    assessment = Assessment.objects.create(configuration=configuration)
    return redirect("assessments:assessment_detail", pk=assessment.pk)


@login_required
def assessment_detail(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    product = _product(assessment.configuration)
    if assessment.status == AssessmentStatus.APPROVED:
        evaluation = assessment.snapshot
    else:
        evaluation = evaluate_configuration(assessment.configuration)
    current, _packages = resolve_answers(assessment.configuration)
    labels = {
        question_id: resolved.question.get("label") or question_id
        for question_id, resolved in current.items()
    }
    answer_rows = [
        {
            "id": question_id,
            "label": labels.get(question_id, question_id),
            "type": current[question_id].question.get("type") if question_id in current else "",
            **answer,
        }
        for question_id, answer in sorted(evaluation.get("resolved_answers", {}).items())
    ]
    configuration = assessment.configuration
    progress = questionnaire_progress(configuration, current)
    is_draft = assessment.status == AssessmentStatus.DRAFT
    can_approve = has_role(request.user, Role.APPROVER, product=product)
    findings = evaluation.get("findings", [])
    workflow = configuration_workflow(configuration, request.user, progress=progress)
    approval_check = None
    if is_draft and can_approve:
        approval_check = {
            "open": progress["open"],
            "findings": {
                level: sum(1 for f in findings if f["level"] == level)
                for level in ("action_required", "caution", "info")
            },
            "risk_state": workflow["risk_state"],
            "risk_entries": workflow["entry_count"],
            "sod": sod_preview(assessment, request.user, current),
        }
    staleness = None
    if assessment.status == AssessmentStatus.APPROVED and assessment.stale:
        report = staleness_report(assessment)
        changed = {a["id"]: a for a in report["answers"]}
        for row in answer_rows:
            if row["id"] in changed:
                row["changed"] = True
                row["now"] = changed[row["id"]]["after"]
        staleness = {
            **report,
            "summary": staleness_summary(report),
            # Answers to questions that no longer apply, or newly apply.
            "other_answers": [
                {**a, "label": labels.get(a["id"], a["id"])}
                for a in report["answers"]
                if a["id"] not in {r["id"] for r in answer_rows}
            ],
        }
    return render(
        request,
        "assessments/assessment_detail.html",
        {
            "assessment": assessment,
            "staleness": staleness,
            "evaluation": evaluation,
            "results": _labelled_results(evaluation.get("results", [])),
            "answer_rows": answer_rows,
            "crumbs": breadcrumbs(
                configuration=configuration, trail=[(f"Assessment #{assessment.pk}", None)]
            ),
            "workflow": workflow,
            "approval_check": approval_check,
            "progress": progress if is_draft else None,
            "readiness": assessment_readiness(assessment.configuration)
            if not evaluation.get("results")
            else [],
            "can_approve": can_approve,
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
        },
    )


def _labelled_results(results) -> list[dict]:
    """Evaluation results with package titles and readable labels for
    classifications, requirements and routes (the evaluation stores ids)."""
    contents = {
        p.pk: p.content
        for p in RequirementPackage.objects.filter(pk__in=[r.get("package_id") for r in results])
    }
    labelled = []
    for result in results:
        content = contents.get(result.get("package_id"), {})

        def labels(key, ids, content=content):
            by_id = {item["id"]: item for item in content.get(key, [])}
            return [
                {
                    "id": item_id,
                    "label": by_id.get(item_id, {}).get("label") or item_id,
                    "ref": by_id.get(item_id, {}).get("ref", ""),
                }
                for item_id in ids
            ]

        labelled.append(
            {
                **result,
                "title": content.get("title") or result["source"],
                "classification_labels": labels("classifications", result["classifications"]),
                "requirement_labels": labels("requirements", result.get("requirements", [])),
                "upcoming_labels": [
                    {**item, "date": r["applies_from"]}
                    for item, r in zip(
                        labels(
                            "requirements",
                            [r["id"] for r in result.get("upcoming_requirements", [])],
                        ),
                        result.get("upcoming_requirements", []),
                        strict=True,
                    )
                ],
                "ended_labels": [
                    {**item, "date": r["applies_until"]}
                    for item, r in zip(
                        labels(
                            "requirements", [r["id"] for r in result.get("ended_requirements", [])]
                        ),
                        result.get("ended_requirements", []),
                        strict=True,
                    )
                ],
                "route_labels": labels("assessment_routes", result.get("assessment_routes", [])),
            }
        )
    return labelled


@login_required
@require_POST
def assessment_approve(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    product = _product(assessment.configuration)
    if not has_role(request.user, Role.APPROVER, product=product):
        django_messages.error(request, "You need the approver role to approve this assessment.")
        return redirect("assessments:assessment_detail", pk=pk)
    open_count = questionnaire_progress(assessment.configuration)["open"]
    if open_count and not request.POST.get("confirm_open"):
        django_messages.error(
            request,
            f"{open_count} questions are still open. Confirm that you approve the assessment "
            "with them open, or answer them first.",
        )
        return redirect(reverse("assessments:assessment_detail", args=[pk]) + "#approve")
    try:
        approve_assessment(assessment, actor=request.user)
        django_messages.success(request, "Assessment approved.")
    except (SoDViolation, AssessmentError) as exc:
        django_messages.error(request, str(exc))
    return redirect("assessments:assessment_detail", pk=pk)
