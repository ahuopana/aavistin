from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST

from apps.core.navigation import breadcrumbs
from apps.orgs.models import Role
from apps.orgs.services import has_role, require_product_view
from apps.products.models import Product
from apps.risk.models import Control

from .models import Evidence, EvidenceKind, EvidenceLink
from .services import (
    EvidenceError,
    EvidenceInUseError,
    copy_links,
    delete_evidence,
    link_evidence,
    parse_requirement_ref,
    requirement_choices,
    store_evidence_file,
    suggest_evidence,
    unlink_evidence,
)

_TARGET_KEYS = ("control", "requirement", "next")


def _safe_next(request, fallback: str) -> str:
    """A same-site return address from ``next`` (GET or POST), else ``fallback``."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return fallback


def _target_from(request, product):
    """The control or requirement a page was opened to attach evidence to
    (``?control=<pk>`` or ``?requirement=source|version|id``), as
    ``{"kind", "label", "control_id" | "requirement"}``; None if neither."""
    params = request.POST if request.method == "POST" else request.GET
    control_pk = params.get("control")
    if control_pk and control_pk.isdigit():
        control = Control.objects.filter(pk=control_pk, product=product).first()
        if control:
            return {"kind": "control", "label": f"Control “{control.name}”", "control": control}
    ref = parse_requirement_ref(params.get("requirement", ""))
    if ref:
        return {
            "kind": "requirement",
            "label": f"Requirement {ref[0]} {ref[2]}",
            "requirement": ref,
            "ref": "|".join(ref),
        }
    return None


def _link_target(evidence, target, actor):
    if target["kind"] == "control":
        return link_evidence(evidence, control=target["control"], actor=actor)
    return link_evidence(evidence, requirement=target["requirement"], actor=actor)


@login_required
def product_evidence_list(request, product_pk):
    product = require_product_view(request.user, get_object_or_404(Product, pk=product_pk))
    return render(
        request,
        "evidence/product_list.html",
        {
            "product": product,
            "crumbs": breadcrumbs(product=product, trail=[("Evidence", None)]),
            "evidence_list": suggest_evidence(product).annotate(link_count=Count("links")),
            "target": _target_from(request, product),
            "next": request.GET.get("next", ""),
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
            "uploads_enabled": settings.UPLOADS_ENABLED,
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
        try:
            evidence.file = store_evidence_file(upload, actor=request.user)
        except EvidenceError as exc:
            django_messages.error(request, str(exc))
            return redirect("evidence:product_list", product_pk=product_pk)

    try:
        evidence.full_clean()
    except ValidationError as exc:
        for field_messages in exc.message_dict.values():
            for message in field_messages:
                django_messages.error(request, message)
        return redirect(
            reverse("evidence:product_list", args=[product_pk])
            + "?"
            + urlencode(
                {
                    k: request.POST[k]
                    for k in ("control", "requirement", "next")
                    if request.POST.get(k)
                }
            )
        )

    supersedes_pk = request.POST.get("supersedes")
    if supersedes_pk:
        evidence.supersedes = get_object_or_404(Evidence, pk=supersedes_pk, product=product)

    evidence.save()
    target = _target_from(request, product)
    if target:
        try:
            _link_target(evidence, target, request.user)
        except (EvidenceError, ValidationError) as exc:
            django_messages.error(request, str(exc))
        else:
            django_messages.success(request, f"Evidence added and linked to {target['label']}.")
            return redirect(_safe_next(request, reverse("evidence:detail", args=[evidence.pk])))
    else:
        django_messages.success(request, "Evidence added.")
    return redirect("evidence:detail", pk=evidence.pk)


@login_required
def evidence_detail(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    require_product_view(request.user, evidence.product)
    return render(
        request,
        "evidence/detail.html",
        {
            "evidence": evidence,
            "crumbs": breadcrumbs(
                product=evidence.product,
                trail=[
                    ("Evidence", reverse("evidence:product_list", args=[evidence.product_id])),
                    (evidence.title, None),
                ],
            ),
            "links": evidence.links.select_related("control").all(),
            "controls": Control.objects.filter(product=evidence.product).order_by("name"),
            "requirements": requirement_choices(evidence.product),
            "newer_versions": evidence.superseded_by.all(),
            "uploads_enabled": settings.UPLOADS_ENABLED,
            "can_edit": has_role(request.user, Role.EDITOR, product=evidence.product),
        },
    )


@login_required
def evidence_download(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    require_product_view(request.user, evidence.product)
    if evidence.file is None or not settings.UPLOADS_ENABLED:
        raise Http404("No downloadable file.")
    stored = evidence.file
    response = FileResponse(
        stored.file.open("rb"),
        as_attachment=True,
        filename=stored.file.name.rsplit("/", 1)[-1],
        content_type=stored.content_type or "application/octet-stream",
    )
    # Uploaded content is untrusted: never let a browser run or sniff it.
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    response["X-Content-Type-Options"] = "nosniff"
    return response


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

    ref = parse_requirement_ref(request.POST.get("requirement_ref", ""))
    source, version, requirement_id = ref or (
        request.POST.get("requirement_source", ""),
        request.POST.get("requirement_version", ""),
        request.POST.get("requirement_id", ""),
    )
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


@login_required
@require_POST
def evidence_attach(request, product_pk):
    """Link an existing evidence record to the control or requirement the
    user came from (reuse over re-upload)."""
    product = get_object_or_404(Product, pk=product_pk)
    fallback = reverse("evidence:product_list", args=[product_pk])
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to link evidence.")
        return redirect(_safe_next(request, fallback))
    evidence = get_object_or_404(Evidence, pk=request.POST.get("evidence_id"), product=product)
    target = _target_from(request, product)
    if target is None:
        django_messages.error(request, "Choose a control or requirement to link to.")
        return redirect(fallback)
    try:
        _link_target(evidence, target, request.user)
        django_messages.success(request, f"Linked “{evidence.title}” to {target['label']}.")
    except (EvidenceError, ValidationError) as exc:
        django_messages.error(request, "; ".join(getattr(exc, "messages", [str(exc)])))
    return redirect(_safe_next(request, fallback))


@login_required
@require_POST
def evidence_edit(request, pk):
    evidence = get_object_or_404(Evidence, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=evidence.product):
        django_messages.error(request, "You need the editor role to edit evidence.")
        return redirect("evidence:detail", pk=pk)

    evidence.title = request.POST.get("title", evidence.title)
    evidence.description = request.POST.get("description", "")
    evidence.valid_until = request.POST.get("valid_until") or None
    audit_date = request.POST.get("last_audit_date") or None
    if request.POST.get("audited_today"):
        audit_date = timezone.now().date()
    if audit_date != evidence.last_audit_date:
        evidence.last_audited_by = request.user if audit_date else None
    evidence.last_audit_date = audit_date
    if evidence.kind == EvidenceKind.LINK:
        evidence.external_url = request.POST.get("external_url", evidence.external_url)
    elif evidence.kind == EvidenceKind.TEXT:
        evidence.reference_text = request.POST.get("reference_text", evidence.reference_text)

    try:
        evidence.full_clean()
    except ValidationError as exc:
        for field_messages in exc.message_dict.values():
            for message in field_messages:
                django_messages.error(request, message)
        return redirect("evidence:detail", pk=pk)
    evidence.save()
    django_messages.success(request, "Evidence updated.")
    return redirect("evidence:detail", pk=pk)


@login_required
@require_POST
def evidence_copy_links(request, pk):
    """On a newer version: relink everything the version it supersedes backs."""
    evidence = get_object_or_404(Evidence, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=evidence.product):
        django_messages.error(request, "You need the editor role to link evidence.")
    elif evidence.supersedes_id is None:
        django_messages.error(request, "This evidence does not supersede an earlier version.")
    else:
        added = copy_links(evidence.supersedes, evidence, actor=request.user)
        django_messages.success(
            request, f"Linked to {added} target{'s' if added != 1 else ''} of the earlier version."
        )
    return redirect("evidence:detail", pk=pk)
