from django.conf import settings
from django.db import models


class PackageType(models.TextChoices):
    LEGISLATION = "legislation", "Legislation"
    HARMONISED_STANDARD = "harmonised_standard", "Harmonised standard"
    QMS = "qms", "QMS / internal procedure"
    CUSTOMER = "customer", "Customer requirement"
    GUIDANCE = "guidance", "Guidance"


class PackageStatus(models.TextChoices):
    DRAFT = "draft", "Draft (failed lint or not yet linted)"
    LINTED = "linted", "Linted clean"
    FIXTURES_PASSED = "fixtures_passed", "Fixtures passed"
    APPROVED = "approved", "Approved / published"
    SUPERSEDED = "superseded", "Superseded"


class RequirementPackage(models.Model):
    """One imported version of a requirement package.

    Only legislation (``package_type=legislation``) creates legal
    obligations; everything else is presumption of conformity, internal,
    contractual or non-binding guidance (see docs/architecture.md,
    "Requirement sources"). The full, schema-validated content is stored
    as JSON; ``source`` + ``version`` identify it, matching the ids used
    inside ``content`` itself and in package files under packages/.
    """

    source = models.CharField(max_length=100)
    version = models.CharField(max_length=100)
    package_type = models.CharField(max_length=32, choices=PackageType.choices)
    jurisdiction = models.CharField(max_length=16)
    title = models.CharField(max_length=200, blank=True, default="")
    content = models.JSONField()
    is_official = models.BooleanField(
        default=False,
        help_text="Official packages live in version control and are maintainer-reviewed.",
    )
    redistributable = models.BooleanField(default=True)

    status = models.CharField(
        max_length=32, choices=PackageStatus.choices, default=PackageStatus.DRAFT
    )
    lint_report = models.JSONField(default=list, blank=True)
    fixture_report = models.JSONField(default=list, blank=True)
    diff_from_previous = models.JSONField(null=True, blank=True)
    supersedes_package = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="superseded_by",
    )

    imported_at = models.DateTimeField(auto_now_add=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["source", "-imported_at"]
        constraints = [
            models.UniqueConstraint(fields=["source", "version"], name="unique_package_version"),
        ]

    def __str__(self):
        return f"{self.source}@{self.version} ({self.status})"

    @property
    def lint_errors(self):
        return [issue for issue in self.lint_report if issue.get("severity") == "error"]

    @property
    def creates_legal_obligations(self) -> bool:
        return self.package_type == PackageType.LEGISLATION
