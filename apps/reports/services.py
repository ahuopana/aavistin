import hashlib
import json
from datetime import datetime

from django.utils import timezone

from .content import (
    SECTION_KEYS,
    build_content,
    issue_blockers,
    latest_approved_assessment,
    latest_approved_risk_assessment,
)
from .models import Report, new_report_id
from .render import render_pdf


class ReportError(Exception):
    pass


def default_title(configuration) -> str:
    return f"{configuration.product.name} – {configuration.name}"


def clean_sections(sections) -> list[str]:
    chosen = [s for s in SECTION_KEYS if s in set(sections)]
    if not chosen:
        raise ReportError("Select at least one section.")
    return chosen


def content_hash(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def generate_draft(
    configuration, sections, *, user, title="", include_out_of_scope=False
) -> bytes:
    """A draft PDF built from live data; nothing is stored (ADR 0041)."""
    content = build_content(
        configuration,
        clean_sections(sections),
        title=title or default_title(configuration),
        generated_by=user,
        generated_at=timezone.now(),
        approved=False,
        include_out_of_scope=include_out_of_scope,
    )
    return render_pdf(content, report_id="", content_hash="")


def issue_report(configuration, sections, *, user, title="", include_out_of_scope=False) -> Report:
    """Store and return an approved, verifiable report."""
    sections = clean_sections(sections)
    blockers = issue_blockers(configuration, sections)
    if blockers:
        raise ReportError(" ".join(blockers))
    generated_at = timezone.now()
    content = build_content(
        configuration,
        sections,
        title=title or default_title(configuration),
        generated_by=user,
        generated_at=generated_at,
        approved=True,
        include_out_of_scope=include_out_of_scope,
    )
    needs_assessment = "assessment" in sections
    needs_risk = "risks" in sections or "mitigations" in sections
    report_id = new_report_id()
    digest = content_hash(content)
    pdf = render_pdf(content, report_id=report_id, content_hash=digest)
    return Report.objects.create(
        report_id=report_id,
        configuration=configuration,
        title=content["title"],
        sections=sections,
        content=content,
        content_sha256=digest,
        pdf=pdf,
        pdf_sha256=hashlib.sha256(pdf).hexdigest(),
        assessment=latest_approved_assessment(configuration) if needs_assessment else None,
        risk_assessment=latest_approved_risk_assessment(configuration) if needs_risk else None,
        generated_by=user,
        generated_by_name=content["generated_by"],
        generated_at=generated_at,
    )


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)
