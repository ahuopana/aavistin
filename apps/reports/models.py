import secrets

from django.conf import settings
from django.db import models

# No 0/O/1/I/L: the id is read aloud and typed from paper.
ID_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def new_report_id() -> str:
    groups = ["".join(secrets.choice(ID_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "AAV-" + "-".join(groups)


class Report(models.Model):
    """An issued, verifiable report of one configuration (ADR 0041).

    Only approved reports are stored; drafts are generated on the fly.
    The row is never edited after creation.
    """

    report_id = models.CharField(max_length=20, unique=True, default=new_report_id, editable=False)
    configuration = models.ForeignKey(
        "products.Configuration", on_delete=models.PROTECT, related_name="reports"
    )
    title = models.CharField(max_length=200)
    sections = models.JSONField(default=list)
    content = models.JSONField()
    content_sha256 = models.CharField(max_length=64)
    pdf = models.BinaryField()
    pdf_sha256 = models.CharField(max_length=64)
    assessment = models.ForeignKey(
        "assessments.Assessment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports",
    )
    risk_assessment = models.ForeignKey(
        "risk.RiskAssessment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reports",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    generated_by_name = models.CharField(max_length=200)
    generated_at = models.DateTimeField()

    class Meta:
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.report_id} {self.title}"

    @property
    def is_current(self) -> bool:
        """False once a source snapshot has gone stale since issue."""
        sources = [s for s in (self.assessment, self.risk_assessment) if s is not None]
        return not any(s.stale for s in sources)
