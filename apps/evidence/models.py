from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

from apps.products.models import Product
from apps.risk.models import Control


def evidence_file_upload_to(instance, filename):
    return f"evidence/{instance.checksum}/{filename}"


class EvidenceFile(models.Model):
    """The stored bytes of an uploaded evidence document, deduplicated
    by content and independent of any one product: see
    docs/architecture.md, "Evidence" ("The blob is not the record").

    Never deleted directly -- apps.evidence.services.delete_evidence
    removes it only once no Evidence record references it any more.
    """

    file = models.FileField(upload_to=evidence_file_upload_to)
    checksum = models.CharField(
        max_length=64, unique=True, help_text="SHA-256 of the file content"
    )
    content_type = models.CharField(max_length=100, blank=True, default="")
    size = models.PositiveBigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    def __str__(self):
        return self.file.name


class EvidenceKind(models.TextChoices):
    FILE = "file", "Uploaded file"
    LINK = "link", "External link"
    TEXT = "text", "Reference note"


class Evidence(models.Model):
    """A piece of proof, scoped to a product and reused across whatever
    it satisfies (docs/architecture.md, "Evidence"). A new document
    version supersedes the old one, the same shape as
    RequirementPackage.supersedes_package; the old version isn't
    silently swapped out under existing links.
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="evidence")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=8, choices=EvidenceKind.choices)

    file = models.ForeignKey(
        EvidenceFile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="evidence",
    )
    external_url = models.URLField(blank=True, default="")
    reference_text = models.TextField(blank=True, default="")

    last_audit_date = models.DateField(null=True, blank=True)
    last_audited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    valid_until = models.DateField(null=True, blank=True)

    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["product__name", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        filled = {
            EvidenceKind.FILE: bool(self.file_id),
            EvidenceKind.LINK: bool(self.external_url),
            EvidenceKind.TEXT: bool(self.reference_text),
        }
        if not filled.get(self.kind):
            raise ValidationError(
                {"kind": f"A '{self.kind}' evidence record needs its matching field filled in."}
            )
        others = [k for k, v in filled.items() if k != self.kind and v]
        if others:
            raise ValidationError(
                f"Only the field matching kind={self.kind!r} may be filled in "
                f"(also set: {', '.join(others)})."
            )

    @property
    def is_expired(self) -> bool:
        return bool(self.valid_until and self.valid_until < timezone.now().date())

    @property
    def is_superseded(self) -> bool:
        return self.superseded_by.exists()


class EvidenceTargetType(models.TextChoices):
    CONTROL = "control", "Risk control"
    REQUIREMENT = "requirement", "Requirement"


class EvidenceLink(models.Model):
    """Attaches one Evidence record to a Control or to a requirement
    reference (docs/architecture.md, "Evidence": "Attaches to two kinds
    of target, both by reference"). A requirement is identified by its
    package's source + version and its own id inside that package's
    content -- never a database row, since individual requirements are
    entries in versioned package JSON, not application-owned records
    (see "Requirement sources"; CLAUDE.md's rule against hard-coding
    regulation scope applies here too).
    """

    evidence = models.ForeignKey(Evidence, on_delete=models.CASCADE, related_name="links")
    target_type = models.CharField(max_length=16, choices=EvidenceTargetType.choices)

    control = models.ForeignKey(
        Control,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evidence_links",
    )
    requirement_source = models.CharField(max_length=100, blank=True, default="")
    requirement_version = models.CharField(max_length=100, blank=True, default="")
    requirement_id = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["evidence", "control"],
                condition=models.Q(target_type=EvidenceTargetType.CONTROL),
                name="unique_evidence_control_link",
            ),
            models.UniqueConstraint(
                fields=["evidence", "requirement_source", "requirement_version", "requirement_id"],
                condition=models.Q(target_type=EvidenceTargetType.REQUIREMENT),
                name="unique_evidence_requirement_link",
            ),
        ]

    def __str__(self):
        if self.target_type == EvidenceTargetType.CONTROL:
            target = self.control_id
        else:
            target = self.requirement_id
        return f"{self.evidence.title} -> {target}"

    def clean(self):
        if self.target_type == EvidenceTargetType.CONTROL:
            if not self.control_id:
                raise ValidationError({"control": "A control-target link needs a control."})
            if self.requirement_source or self.requirement_version or self.requirement_id:
                raise ValidationError(
                    "A control-target link cannot also carry requirement fields."
                )
            if self.control.product_id != self.evidence.product_id:
                raise ValidationError(
                    {"control": "The control must belong to the same product as the evidence."}
                )
        elif self.target_type == EvidenceTargetType.REQUIREMENT:
            if not (self.requirement_source and self.requirement_version and self.requirement_id):
                raise ValidationError(
                    "A requirement-target link needs requirement_source, "
                    "requirement_version and requirement_id."
                )
            if self.control_id:
                raise ValidationError(
                    {"control": "A requirement-target link cannot also carry a control."}
                )
