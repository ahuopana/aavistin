from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.products.models import Configuration

from .evaluation import evaluate_configuration
from .models import Answer, Assessment, AssessmentStatus
from .resolution import resolve_answers
from .services import AssessmentError, SoDViolation, approve_assessment

LEVEL_TO_OWNER_FIELD = {
    "product": "product",
    "hardware": "hardware_revision",
    "software": "software_release",
    "option": "software_option",
}


def _product_family(configuration):
    return configuration.hardware_revision.hardware_variant.product.product_family


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


@login_required
def configuration_detail(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    family = _product_family(configuration)
    resolved, _packages = resolve_answers(configuration)

    product = configuration.hardware_revision.hardware_variant.product
    first_option = configuration.software_options.order_by("id").first()
    owner_by_level = {
        "product": product,
        "hardware": configuration.hardware_revision,
        "software": configuration.software_release,
        "option": first_option,
    }

    rows = []
    for _question_id, resolved_answer in sorted(resolved.items()):
        level = resolved_answer.question.get("level")
        owner = owner_by_level.get(level)
        rows.append(
            {
                "question": resolved_answer.question,
                "value": resolved_answer.value,
                "origin": resolved_answer.origin,
                "needs_confirmation": resolved_answer.needs_confirmation,
                "owner_type": LEVEL_TO_OWNER_FIELD.get(level),
                "owner_id": owner.pk if owner else None,
            }
        )

    return render(
        request,
        "assessments/configuration_detail.html",
        {
            "configuration": configuration,
            "product": product,
            "rows": rows,
            "assessments": configuration.assessments.all(),
            "can_edit": has_role(request.user, Role.EDITOR, product_family=family),
            "justification_help": Answer._meta.get_field("override_justification").help_text,
        },
    )


@login_required
@require_POST
def answer_question(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    family = _product_family(configuration)
    if not has_role(request.user, Role.EDITOR, product_family=family):
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
    owner_field = f"{owner_type}_id"
    question_type = request.POST.get("question_type", "")
    value = _coerce_value(request.POST.get("value", ""), question_type)
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
    return redirect("assessments:configuration_detail", pk=pk)


@login_required
@require_POST
def assessment_create(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    family = _product_family(configuration)
    if not has_role(request.user, Role.EDITOR, product_family=family):
        django_messages.error(request, "You need the editor role to start an assessment.")
        return redirect("assessments:configuration_detail", pk=pk)
    assessment = Assessment.objects.create(configuration=configuration)
    return redirect("assessments:assessment_detail", pk=assessment.pk)


@login_required
def assessment_detail(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    family = _product_family(assessment.configuration)
    if assessment.status == AssessmentStatus.APPROVED:
        evaluation = assessment.snapshot
    else:
        evaluation = evaluate_configuration(assessment.configuration)
    return render(
        request,
        "assessments/assessment_detail.html",
        {
            "assessment": assessment,
            "evaluation": evaluation,
            "can_approve": has_role(request.user, Role.APPROVER, product_family=family),
        },
    )


@login_required
@require_POST
def assessment_approve(request, pk):
    assessment = get_object_or_404(Assessment, pk=pk)
    family = _product_family(assessment.configuration)
    if not has_role(request.user, Role.APPROVER, product_family=family):
        django_messages.error(request, "You need the approver role to approve this assessment.")
        return redirect("assessments:assessment_detail", pk=pk)
    try:
        approve_assessment(assessment, actor=request.user)
        django_messages.success(request, "Assessment approved.")
    except (SoDViolation, AssessmentError) as exc:
        django_messages.error(request, str(exc))
    return redirect("assessments:assessment_detail", pk=pk)
