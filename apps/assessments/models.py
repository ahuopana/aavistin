from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.products.models import (
    Configuration,
    HardwareRevision,
    Product,
    SoftwareOption,
    SoftwareRelease,
)

_UNSET = object()

# Precedence, most specific first, matching docs/architecture.md,
# "Answer inheritance": option -> SW release -> HW variant -> product.
# "HW variant" in the prose is the HardwareRevision here — see
# docs/adr/0004-answer-levels-and-precedence.md.
OWNER_FIELDS = ["software_option", "software_release", "hardware_revision", "product"]


class Answer(models.Model):
    """A directly-entered answer, attached to one entity in the product hierarchy.

    Not attached to a specific Assessment: the same product-level answer
    is shared by every configuration of that product, and is resolved
    (with more specific levels overriding it) at assessment time. See
    apps/assessments/resolution.py.
    """

    question_id = models.CharField(max_length=100)
    value = models.JSONField()
    override_justification = models.TextField(blank=True, default="")
    needs_confirmation = models.BooleanField(
        default=False,
        help_text="Set when carried forward from a previous software release; "
        "a reviewer must confirm it actively.",
    )

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, null=True, blank=True, related_name="answers"
    )
    hardware_revision = models.ForeignKey(
        HardwareRevision, on_delete=models.CASCADE, null=True, blank=True, related_name="answers"
    )
    software_release = models.ForeignKey(
        SoftwareRelease, on_delete=models.CASCADE, null=True, blank=True, related_name="answers"
    )
    software_option = models.ForeignKey(
        SoftwareOption, on_delete=models.CASCADE, null=True, blank=True, related_name="answers"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        product__isnull=False,
                        hardware_revision__isnull=True,
                        software_release__isnull=True,
                        software_option__isnull=True,
                    )
                    | models.Q(
                        product__isnull=True,
                        hardware_revision__isnull=False,
                        software_release__isnull=True,
                        software_option__isnull=True,
                    )
                    | models.Q(
                        product__isnull=True,
                        hardware_revision__isnull=True,
                        software_release__isnull=False,
                        software_option__isnull=True,
                    )
                    | models.Q(
                        product__isnull=True,
                        hardware_revision__isnull=True,
                        software_release__isnull=True,
                        software_option__isnull=False,
                    )
                ),
                name="answer_exactly_one_owner",
            ),
            models.UniqueConstraint(
                fields=["product", "question_id"],
                condition=models.Q(product__isnull=False),
                name="unique_answer_per_product_question",
            ),
            models.UniqueConstraint(
                fields=["hardware_revision", "question_id"],
                condition=models.Q(hardware_revision__isnull=False),
                name="unique_answer_per_hw_revision_question",
            ),
            models.UniqueConstraint(
                fields=["software_release", "question_id"],
                condition=models.Q(software_release__isnull=False),
                name="unique_answer_per_sw_release_question",
            ),
            models.UniqueConstraint(
                fields=["software_option", "question_id"],
                condition=models.Q(software_option__isnull=False),
                name="unique_answer_per_sw_option_question",
            ),
        ]

    def __str__(self):
        return f"{self.question_id}={self.value!r} @ {self.owner}"

    @property
    def owner(self):
        return (
            self.product or self.hardware_revision or self.software_release or self.software_option
        )

    @property
    def owner_level(self) -> str:
        for field in OWNER_FIELDS:
            if getattr(self, f"{field}_id"):
                return field
        raise ValueError("Answer has no owner set")

    def ancestor_chain(self):
        """The broader entities in the precedence chain, nearest first.

        option -> [software_release, product]; software_release ->
        [product]; hardware_revision -> [product]; product -> [].
        """
        if self.software_option_id:
            release = self.software_option.software_release
            return [("software_release", release), ("product", release.product)]
        if self.software_release_id:
            return [("product", self.software_release.product)]
        if self.hardware_revision_id:
            return [("product", self.hardware_revision.hardware_variant.product)]
        return []

    def clean(self):
        owners = [
            self.product_id,
            self.hardware_revision_id,
            self.software_release_id,
            self.software_option_id,
        ]
        if sum(bool(o) for o in owners) != 1:
            raise ValidationError(
                "Set exactly one of product/hardware_revision/software_release/software_option."
            )

        ancestor_value = self._ancestor_value()
        if (
            ancestor_value is not _UNSET
            and ancestor_value != self.value
            and not self.override_justification
        ):
            raise ValidationError(
                {
                    "override_justification": (
                        "This answer overrides one inherited from a broader level; "
                        "a justification is required."
                    )
                }
            )

    def _ancestor_value(self):
        """The value this question would currently resolve to, ignoring this
        answer — i.e. the first stored answer found further up the
        precedence chain — or _UNSET if none exists."""
        for field, owner in self.ancestor_chain():
            ancestor_answer = (
                Answer.objects.filter(**{field: owner, "question_id": self.question_id})
                .exclude(pk=self.pk)
                .first()
            )
            if ancestor_answer is not None:
                return ancestor_answer.value
        return _UNSET


class AssessmentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"


class Assessment(models.Model):
    """Covers one Configuration. Approval freezes a snapshot of the
    resolved answers, active package versions, results and findings at
    that moment; later changes never alter it, only mark it stale."""

    configuration = models.ForeignKey(
        Configuration, on_delete=models.PROTECT, related_name="assessments"
    )
    status = models.CharField(
        max_length=16, choices=AssessmentStatus.choices, default=AssessmentStatus.DRAFT
    )
    snapshot = models.JSONField(null=True, blank=True)
    stale = models.BooleanField(default=False)
    sod_warning = models.BooleanField(
        default=False,
        help_text="Set if approved by someone who also edited an answer in the "
        "snapshot, under a 'warn' separation-of-duties policy.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Assessment #{self.pk} of {self.configuration} ({self.status})"
