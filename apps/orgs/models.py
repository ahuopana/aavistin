from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords


class SoDPolicy(models.TextChoices):
    """Separation-of-duties enforcement level.

    Ordered from loosest to strictest; a child scope may only tighten this
    (move up the order), never loosen it. See docs/architecture.md,
    "Organisations and roles".
    """

    OFF = "off", "Off"
    WARN = "warn", "Warn"
    ENFORCE = "enforce", "Enforce"


SOD_POLICY_ORDER = {
    SoDPolicy.OFF: 0,
    SoDPolicy.WARN: 1,
    SoDPolicy.ENFORCE: 2,
}


class Organisation(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    sod_policy = models.CharField(
        max_length=16,
        choices=SoDPolicy.choices,
        default=SoDPolicy.WARN,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ProductFamily(models.Model):
    organisation = models.ForeignKey(
        Organisation, on_delete=models.CASCADE, related_name="product_families"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    sod_policy_override = models.CharField(
        max_length=16,
        choices=SoDPolicy.choices,
        blank=True,
        default="",
        help_text="Leave unset to inherit the organisation's policy. May only tighten it.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["organisation__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organisation", "slug"], name="unique_family_slug_per_org"
            ),
        ]

    def __str__(self):
        return f"{self.organisation.name} / {self.name}"

    def clean(self):
        if self.sod_policy_override:
            override_rank = SOD_POLICY_ORDER[self.sod_policy_override]
            org_rank = SOD_POLICY_ORDER[self.organisation.sod_policy]
            if override_rank < org_rank:
                raise ValidationError(
                    {
                        "sod_policy_override": (
                            "A product family may only tighten the organisation's "
                            "separation-of-duties policy, never loosen it."
                        )
                    }
                )

    @property
    def effective_sod_policy(self) -> str:
        return self.sod_policy_override or self.organisation.sod_policy


class Role(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    EDITOR = "editor", "Editor"
    APPROVER = "approver", "Approver"
    CONTENT_CURATOR = "content_curator", "Content curator"
    ORG_ADMIN = "org_admin", "Organisation admin"


class RoleAssignment(models.Model):
    """A (user or group, role, scope) grant, inherited down the hierarchy.

    Exactly one of ``user``/``group`` and exactly one of
    ``organisation``/``product_family`` must be set. A grant at
    ``organisation`` scope applies to every product family (and, from
    Milestone 3, product) beneath it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    product_family = models.ForeignKey(
        ProductFamily,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(user__isnull=False, group__isnull=True)
                    | models.Q(user__isnull=True, group__isnull=False)
                ),
                name="role_assignment_exactly_one_of_user_or_group",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(organisation__isnull=False, product_family__isnull=True)
                    | models.Q(organisation__isnull=True, product_family__isnull=False)
                ),
                name="role_assignment_exactly_one_scope",
            ),
        ]

    def __str__(self):
        grantee = self.user or self.group
        scope = self.organisation or self.product_family
        return f"{grantee} — {self.role} @ {scope}"

    def clean(self):
        if bool(self.user_id) == bool(self.group_id):
            raise ValidationError("Set exactly one of user or group.")
        if bool(self.organisation_id) == bool(self.product_family_id):
            raise ValidationError("Set exactly one of organisation or product_family.")
