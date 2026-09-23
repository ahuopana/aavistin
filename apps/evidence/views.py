from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.products.models import Product
from apps.risk.models import Control

from .models import Evidence, EvidenceKind, EvidenceLink
from .services import (
    EvidenceError,
    EvidenceInUseError,
    delete_evidence,
    link_evidence,
    store_evidence_file,
    suggest_evidence,
    unlink_evidence,
)


@login_required
def product_evidence_list(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    return render(
        request,
        "evidence/product_list.html",
        {
            "product": product,
            "evidence_list": suggest_evidence(product),
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
        },
    )


@login_required
@require_POST
def evidence_create(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add evidence.")
        return redirect("evidence:product_list", product_pk=product_pk)

    kind = request.POST.get("kind", "")
    evidence = Evidence(
        product=product,
        title=request.POST.get("title", ""),
        description=request.POST.get("description", ""),
        kind=kind,
        external_url=request.POST.get("external_url", ""),
        reference_text=request.POST.get("reference_text", ""),
    )
    upload = request.FILES.get("file")
    if kind == EvidenceKind.FILE and upload:
        evidence.file = store_evidence_file(upload, actor=request.user)

    try:
        evidence.full_clean()
    except ValidationError as exc:
        for field_messages in exc.message_dict.values():
            for message in field_messages:
                django_messages.error(request, message)
        return redirect("evidence:product_list", product_pk=product_pk)

    evidence.save()
    django_messages.success(request, "Evidence added.")
    return redirect("evidence:detail", pk=evidence.pk)


@login_required
def evidence_detail(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    return render(
        request,
        "evidence/detail.html",
        {
            "evidence": evidence,
            "links": evidence.links.select_related("control").all(),
            "controls": Control.objects.filter(product=evidence.product).order_by("name"),
            "can_edit": has_role(request.user, Role.EDITOR, product=evidence.product),
        },
    )


@login_required
@require_POST
def evidence_link_control(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=evidence.product):
        django_messages.error(request, "You need the editor role to link evidence.")
        return redirect("evidence:detail", pk=pk)

    control = get_object_or_404(
        Control, pk=request.POST.get("control_id"), product=evidence.product
    )
    try:
        link_evidence(evidence, control=control, actor=request.user)
        django_messages.success(request, f"Linked to {control}.")
    except (EvidenceError, ValidationError) as exc:
        django_messages.error(request, str(exc))
    return redirect("evidence:detail", pk=pk)


@login_required
@require_POST
def evidence_link_requirement(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=evidence.product):
        django_messages.error(request, "You need the editor role to link evidence.")
        return redirect("evidence:detail", pk=pk)

    source = request.POST.get("requirement_source", "")
    version = request.POST.get("requirement_version", "")
    requirement_id = request.POST.get("requirement_id", "")
    try:
        link_evidence(evidence, requirement=(source, version, requirement_id), actor=request.user)
        django_messages.success(request, f"Linked to {source} {requirement_id}.")
    except (EvidenceError, ValidationError) as exc:
        django_messages.error(request, str(exc))
    return redirect("evidence:detail", pk=pk)


@login_required
@require_POST
def evidence_unlink(request, link_pk):
    link = get_object_or_404(EvidenceLink, pk=link_pk)
    evidence = link.evidence
    if not has_role(request.user, Role.EDITOR, product=evidence.product):
        django_messages.error(request, "You need the editor role to unlink evidence.")
        return redirect("evidence:detail", pk=evidence.pk)
    unlink_evidence(link)
    return redirect("evidence:detail", pk=evidence.pk)


@login_required
@require_POST
def evidence_delete(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=evidence.product):
        django_messages.error(request, "You need the editor role to delete evidence.")
        return redirect("evidence:detail", pk=pk)

    product_pk = evidence.product_id
    try:
        delete_evidence(evidence)
        django_messages.success(request, "Evidence deleted.")
    except EvidenceInUseError as exc:
        django_messages.error(request, str(exc))
        return redirect("evidence:detail", pk=pk)
    return redirect("evidence:product_list", product_pk=product_pk)
