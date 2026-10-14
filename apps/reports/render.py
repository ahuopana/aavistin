from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML


def render_pdf(content: dict, *, report_id: str, content_hash: str) -> bytes:
    """Render stored report content to PDF bytes. Pure function of its inputs."""
    html = render_to_string(
        "reports/pdf.html",
        {
            "c": content,
            "report_id": report_id,
            "content_hash": content_hash,
            "draft": content["status"] != "approved",
            "logo": settings.BASE_DIR / "static" / "img" / "aavistin-lockup-horizontal.svg",
        },
    )
    return HTML(string=html, base_url=str(settings.BASE_DIR)).write_pdf()
