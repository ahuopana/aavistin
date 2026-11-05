import hashlib
import io

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core import throttle
from apps.core.navigation import breadcrumbs
from apps.orgs.models import Role
from apps.orgs.services import has_role, roles_for_user
from apps.products.models import Configuration

from .content import SECTIONS, issue_blockers
from .models import Report
from .services import ReportError, default_title, generate_draft, issue_report

VERIFY_SCOPE = "verify"

DEFAULT_SECTIONS = [
    "product",
    "hardware",
    "software",
    "options",
    "assessment",
    "risks",
    "mitigations",
]


def _can_view(user, product) -> bool:
    return user.is_superuser or bool(roles_for_user(user, product=product))


def _can_issue(user, product) -> bool:
    return user.is_superuser or has_role(user, Role.APPROVER, product=product)


@login_required
def report_generate(request, configuration_pk):
    configuration = get_object_or_404(
        Configuration.objects.select_related(
            "software_release__product__product_family__organisation"
        ),
        pk=configuration_pk,
    )
    product = configuration.product
    if not _can_view(request.user, product):
        django_messages.error(request, "You need a role on this product to see it.")
        return redirect("orgs:portfolio")

    selected = request.POST.getlist("sections") if request.method == "POST" else DEFAULT_SECTIONS
    title = request.POST.get("title", "").strip() if request.method == "POST" else ""
    include_out_of_scope = request.method == "POST" and "include_out_of_scope" in request.POST
    can_issue = _can_issue(request.user, product)
    blockers = issue_blockers(configuration, selected)

    if request.method == "POST":
        try:
            if request.POST.get("action") == "issue":
                if not can_issue:
                    django_messages.error(
                        request, "Only an approver can issue an approved report."
                    )
                else:
                    report = issue_report(
                        configuration,
                        selected,
                        user=request.user,
                        title=title,
                        include_out_of_scope=include_out_of_scope,
                    )
                    return redirect("reports:detail", report_id=report.report_id)
            else:
                pdf = generate_draft(
                    configuration,
                    selected,
                    user=request.user,
                    title=title,
                    include_out_of_scope=include_out_of_scope,
                )
                response = HttpResponse(pdf, content_type="application/pdf")
                response["Content-Disposition"] = 'attachment; filename="draft-report.pdf"'
                return response
        except ReportError as error:
            django_messages.error(request, str(error))

    return render(
        request,
        "reports/generate.html",
        {
            "configuration": configuration,
            "product": product,
            "crumbs": breadcrumbs(configuration=configuration, trail=[("Report", None)]),
            "sections": SECTIONS,
            "selected": selected,
            "title": title or default_title(configuration),
            "include_out_of_scope": include_out_of_scope,
            "can_issue": can_issue,
            "blockers": blockers,
        },
    )


@login_required
def report_list(request):
    reports = Report.objects.select_related(
        "configuration__software_release__product__product_family", "assessment", "risk_assessment"
    )
    visible = [r for r in reports if _can_view(request.user, r.configuration.product)]
    return render(request, "reports/list.html", {"reports": visible})


def _visible_report(request, report_id):
    report = get_object_or_404(Report.objects.select_related("configuration"), report_id=report_id)
    if not _can_view(request.user, report.configuration.product):
        raise Http404
    return report


@login_required
def report_detail(request, report_id):
    report = _visible_report(request, report_id)
    return render(
        request,
        "reports/detail.html",
        {"report": report, "verify_enabled": settings.REPORT_VERIFY_ENABLED},
    )


@login_required
def report_pdf(request, report_id):
    report = _visible_report(request, report_id)
    return FileResponse(
        io.BytesIO(bytes(report.pdf)),
        content_type="application/pdf",
        as_attachment=True,
        filename=f"{report.report_id}.pdf",
    )


def verify(request, report_id):
    """Public check of an issued report. Drafts are never stored, so a draft
    id and an unknown id are indistinguishable (ADR 0041).

    Unauthenticated, so it can be switched off (``REPORT_VERIFY_ENABLED``), is
    rate limited per client address, and caps and streams the uploaded file
    (ADR 0049)."""
    if not settings.REPORT_VERIFY_ENABLED:
        raise Http404("Report verification is disabled.")
    ip = throttle.client_ip(request)
    wait = throttle.retry_after(
        VERIFY_SCOPE,
        ip,
        limit=settings.REPORT_VERIFY_RATE_LIMIT,
        window=settings.REPORT_VERIFY_RATE_WINDOW_SECONDS,
    )
    if wait:
        response = HttpResponse("Too many requests. Try again later.", status=429)
        response["Retry-After"] = str(wait)
        return response
    throttle.record(VERIFY_SCOPE, ip)

    report = Report.objects.filter(report_id=report_id.upper()).first()
    result = None
    error = ""
    upload = request.FILES.get("pdf") if request.method == "POST" else None
    if report is not None and upload is not None:
        if upload.size > settings.REPORT_VERIFY_MAX_BYTES:
            error = (
                f"The file is larger than the {settings.REPORT_VERIFY_MAX_BYTES // (1024 * 1024)}"
                " MB limit."
            )
        else:
            hasher = hashlib.sha256()
            for chunk in upload.chunks():
                hasher.update(chunk)
            result = "match" if hasher.hexdigest() == report.pdf_sha256 else "mismatch"
    return render(
        request,
        "reports/verify.html",
        {"report": report, "report_id": report_id, "result": result, "error": error},
        status=200 if report else 404,
    )
