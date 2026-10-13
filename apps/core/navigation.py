"""Where am I, what is the next step, and what waits for my approval?

Three read-side helpers shared by several pages (see
docs/adr/0032-navigation-and-workflow-guidance.md):

- ``breadcrumbs``: the trail Portfolio / Organisation / Family / Product /
  Configuration / ... for any page below the portfolio.
- ``configuration_workflow``: one configuration's progress through
  Questions -> Assessment -> Risk register -> Approval, and the next step
  for the current user. Derived on each request, never stored.
- ``approval_items``: what the user, as an approver, could approve now.
"""

from django.urls import reverse

from apps.assessments.models import AssessmentStatus
from apps.assessments.progress import questionnaire_progress
from apps.assessments.services import staleness_report, staleness_summary
from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    ProductStatus,
    SoftwareOption,
    SoftwareRelease,
)
from apps.products.services import editable_products
from apps.risk.models import RiskAssessmentStatus
from apps.risk.resolution import register_for_configuration
from apps.risk.suggestions import pending_suggestions

DONE, CURRENT, TODO = "done", "current", "todo"


def product_of_configuration(configuration):
    return configuration.hardware_revision.hardware_variant.product


def breadcrumbs(*, product=None, configuration=None, trail=()) -> list[dict]:
    """``[{"label", "url"}]`` from the portfolio down; the last crumb is the
    current page and has no url. ``trail`` adds ``(label, url)`` pairs below
    the configuration (or product)."""
    if configuration is not None and product is None:
        product = product_of_configuration(configuration)
    crumbs = [{"label": "Portfolio", "url": reverse("orgs:portfolio")}]
    if product is not None:
        family = product.product_family
        organisation = family.organisation
        crumbs += [
            {"label": organisation.name, "url": reverse("orgs:detail", args=[organisation.slug])},
            {"label": family.name, "url": reverse("orgs:portfolio") + f"#family-{family.pk}"},
            {"label": product.name, "url": reverse("products:product_detail", args=[product.pk])},
        ]
    if configuration is not None:
        crumbs.append(
            {
                "label": configuration.name,
                "url": reverse("assessments:configuration_detail", args=[configuration.pk]),
            }
        )
    crumbs += [{"label": label, "url": url} for label, url in trail]
    crumbs[-1] = {**crumbs[-1], "url": None}
    return crumbs


def latest_risk_assessment(configuration):
    return configuration.risk_assessments.order_by("-created_at").first()


def _approval_state(record, approved_value) -> str:
    """'none', 'draft', 'approved' or 'stale' for an assessment-like record."""
    if record is None:
        return "none"
    if record.status != approved_value:
        return "draft"
    return "stale" if record.stale else "approved"


STATE_LABELS = {
    "none": "Not started",
    "draft": "Draft",
    "approved": "Approved",
    "stale": "Stale, needs re-review",
}


def _assessment_detail(assessment, state) -> str:
    """The Assessment step's detail line; for a stale one, what changed."""
    if state != "stale":
        return STATE_LABELS[state]
    summary = staleness_summary(staleness_report(assessment))
    return f"Stale: {summary} changed" if summary else STATE_LABELS[state]


def configuration_workflow(configuration, user, *, progress=None, entries=None, pending=None):
    """Steps and the next action for ``configuration``, from ``user``'s roles.

    Pass ``progress`` (questionnaire_progress), ``entries``
    (register_for_configuration) or ``pending`` (pending_suggestions) when
    the caller already has them, to avoid computing them twice.
    """
    product = product_of_configuration(configuration)
    can_edit = has_role(user, Role.EDITOR, product=product)
    can_approve = has_role(user, Role.APPROVER, product=product)
    if progress is None:
        progress = questionnaire_progress(configuration)
    if entries is None:
        entries = register_for_configuration(configuration)
    if pending is None:
        pending = pending_suggestions(configuration)

    questionnaire_url = reverse("assessments:configuration_detail", args=[configuration.pk])
    register_url = reverse("risk:register", args=[configuration.pk])

    assessment = configuration.assessments.order_by("-created_at").first()
    assessment_state = _approval_state(assessment, AssessmentStatus.APPROVED)
    assessment_url = (
        reverse("assessments:assessment_detail", args=[assessment.pk])
        if assessment
        else questionnaire_url + "#assessments"
    )
    risk_assessment = latest_risk_assessment(configuration)
    risk_state = _approval_state(risk_assessment, RiskAssessmentStatus.APPROVED)

    questions_done = progress["total"] > 0 and progress["open"] == 0
    register_done = bool(entries) and not pending
    approval_done = (
        assessment_state == "approved" and risk_state == "approved" and configuration.is_approved
    )

    if not progress["total"]:
        questions_detail = "No questions apply yet"
    else:
        questions_detail = f"{progress['done']} of {progress['total']} answered"
    register_detail = f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}"
    if pending:
        register_detail += (
            f", {len(pending)} suggestion{'s' if len(pending) != 1 else ''} to review"
        )

    steps = [
        {
            "key": "questions",
            "label": "Questions",
            "done": questions_done,
            "detail": questions_detail,
            "url": questionnaire_url + ("?show=open" if progress["open"] else "") + "#questions",
        },
        {
            "key": "assessment",
            "label": "Assessment",
            "done": assessment_state == "approved",
            "detail": _assessment_detail(assessment, assessment_state),
            "state": assessment_state,
            "url": assessment_url,
        },
        {
            "key": "risk",
            "label": "Risk register",
            "done": register_done,
            "detail": register_detail,
            "url": register_url,
        },
        {
            "key": "approval",
            "label": "Approval",
            "done": approval_done,
            "detail": f"Assessment: {STATE_LABELS[assessment_state].lower()}; "
            f"risk register: {STATE_LABELS[risk_state].lower()}; "
            f"configuration: {'approved' if configuration.is_approved else 'draft'}",
            "state": risk_state,
            "url": register_url + "#approval",
        },
    ]

    next_step = _next_step(
        configuration,
        progress=progress,
        assessment=assessment,
        assessment_state=assessment_state,
        entries=entries,
        pending=pending,
        risk_state=risk_state,
        can_edit=can_edit,
        can_approve=can_approve,
        urls={"questionnaire": questionnaire_url, "register": register_url},
    )
    current_key = next_step.get("step")
    for step in steps:
        step["state_class"] = (
            DONE if step["done"] else CURRENT if step["key"] == current_key else TODO
        )
    return {
        "configuration": configuration,
        "steps": steps,
        "next": next_step,
        "assessment": assessment,
        "assessment_state": assessment_state,
        "risk_assessment": risk_assessment,
        "risk_state": risk_state,
        "progress": progress,
        "entry_count": len(entries),
        "pending_count": len(pending),
    }


def _next_step(
    configuration,
    *,
    progress,
    assessment,
    assessment_state,
    entries,
    pending,
    risk_state,
    can_edit,
    can_approve,
    urls,
) -> dict:
    """``{"step", "label", "url" | "post_url", "waiting"}``: the one thing to
    do next. ``waiting`` marks a step someone else (another role) has to do."""
    if progress["total"] and progress["open"]:
        if can_edit:
            return {
                "step": "questions",
                "label": f"Answer {progress['open']} open question"
                + ("s" if progress["open"] != 1 else ""),
                "url": urls["questionnaire"] + "?show=open#questions",
            }
        return {
            "step": "questions",
            "label": "Questions are still being answered",
            "waiting": True,
        }
    if assessment is None:
        if can_edit:
            return {
                "step": "assessment",
                "label": "Start the assessment",
                "post_url": reverse("assessments:assessment_create", args=[configuration.pk]),
            }
        return {
            "step": "assessment",
            "label": "Waiting for an editor to start the assessment",
            "waiting": True,
        }
    if assessment_state == "stale":
        # An approved assessment is never approved again: re-review starts a
        # new draft, which an approver then approves.
        if can_edit:
            return {
                "step": "assessment",
                "label": "Start a new assessment to re-review",
                "post_url": reverse("assessments:assessment_create", args=[configuration.pk]),
            }
        return {
            "step": "assessment",
            "label": "Waiting for an editor to start a new assessment",
            "waiting": True,
        }
    if pending:
        if can_edit:
            return {
                "step": "risk",
                "label": f"Review {len(pending)} suggested risk entr"
                + ("ies" if len(pending) != 1 else "y"),
                "url": reverse("risk:suggestions", args=[configuration.pk]),
            }
        return {
            "step": "risk",
            "label": "Risk suggestions are waiting for review",
            "waiting": True,
        }
    if not entries:
        if can_edit:
            return {
                "step": "risk",
                "label": "Add the first risk register entry",
                "url": reverse("risk:entry_create", args=[configuration.pk]),
            }
        return {"step": "risk", "label": "Waiting for the risk register", "waiting": True}
    if assessment_state == "draft":
        url = reverse("assessments:assessment_detail", args=[assessment.pk]) + "#approve"
        if can_approve:
            return {"step": "approval", "label": "Review and approve the assessment", "url": url}
        return {
            "step": "approval",
            "label": "Waiting for an approver: assessment",
            "waiting": True,
        }
    if risk_state != "approved":
        if can_approve:
            return {
                "step": "approval",
                "label": "Review and approve the risk register",
                "url": urls["register"] + "#approval",
            }
        return {
            "step": "approval",
            "label": "Waiting for an approver: risk register",
            "waiting": True,
        }
    if not configuration.is_approved:
        if can_approve:
            product = product_of_configuration(configuration)
            return {
                "step": "approval",
                "label": "Approve the configuration",
                "url": reverse("products:product_detail", args=[product.pk])
                + "?tab=configurations",
            }
        return {
            "step": "approval",
            "label": "Waiting for an approver: configuration",
            "waiting": True,
        }
    return {"step": None, "label": "All steps are complete", "done": True}


def approval_items(user) -> list[dict]:
    """What ``user`` could approve now, grouped by product:
    ``[{"product", "items": [{"kind", "label", "url"}]}]``."""
    groups = []
    products = (
        editable_products(user, role=Role.APPROVER)
        .exclude(status__in=[ProductStatus.ARCHIVED])
        .select_related("product_family__organisation")
        .order_by("product_family__organisation__name", "product_family__name", "name")
    )
    for product in products:
        product_url = reverse("products:product_detail", args=[product.pk])
        items = []
        if product.status == ProductStatus.DRAFT:
            items.append({"kind": "Product", "label": product.name, "url": product_url})
        for model, kind, tab in (
            (HardwareVariant.objects.filter(product=product), "Hardware variant", "hardware"),
            (
                HardwareRevision.objects.filter(hardware_variant__product=product),
                "Hardware revision",
                "hardware",
            ),
            (SoftwareRelease.objects.filter(product=product), "Software release", "software"),
            (
                SoftwareOption.objects.filter(software_release__product=product),
                "Software option",
                "software",
            ),
        ):
            for instance in model.filter(is_approved=False):
                items.append(
                    {"kind": kind, "label": str(instance), "url": f"{product_url}?tab={tab}"}
                )
        configurations = Configuration.objects.filter(
            hardware_revision__hardware_variant__product=product
        ).order_by("name")
        for configuration in configurations:
            if not configuration.is_approved:
                items.append(
                    {
                        "kind": "Configuration",
                        "label": configuration.name,
                        "url": f"{product_url}?tab=configurations",
                    }
                )
            assessment = configuration.assessments.order_by("-created_at").first()
            state = _approval_state(assessment, AssessmentStatus.APPROVED)
            # A stale approved assessment needs a new draft first (an editor's
            # step), so only drafts are listed.
            if state == "draft":
                open_count = questionnaire_progress(configuration)["open"]
                note = f" ({open_count} questions still open)" if open_count else ""
                items.append(
                    {
                        "kind": "Assessment",
                        "label": f"{configuration.name}, #{assessment.pk}{note}",
                        "url": reverse("assessments:assessment_detail", args=[assessment.pk])
                        + "#approve",
                    }
                )
            risk_state = _approval_state(
                latest_risk_assessment(configuration), RiskAssessmentStatus.APPROVED
            )
            if risk_state != "approved" and register_for_configuration(configuration):
                items.append(
                    {
                        "kind": "Stale risk register"
                        if risk_state == "stale"
                        else "Risk register",
                        "label": configuration.name,
                        "url": reverse("risk:register", args=[configuration.pk]) + "#approval",
                    }
                )
        if items:
            groups.append({"product": product, "items": items})
    return groups


def is_approver_anywhere(user) -> bool:
    """Cheap check for showing the Approvals nav link."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return editable_products(user, role=Role.APPROVER).exists()
