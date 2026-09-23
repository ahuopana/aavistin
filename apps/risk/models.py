from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from apps.packages.models import RequirementPackage
from apps.products.models import (
    Configuration,
    HardwareVariant,
    Product,
    SoftwareOption,
    SoftwareRelease,
)


class EntryType(models.TextChoices):
    ASSET = "asset", "Asset"
    THREAT = "threat", "Threat"
    HAZARD = "hazard", "Hazard"


class SuggestionStatus(models.TextChoices):
    CUSTOM = "custom", "Custom (added manually)"
    PENDING = "pending", "Suggested, pending review"
    ACCEPTED = "accepted", "Suggested, accepted"
    DISMISSED = "dismissed", "Suggested, dismissed"


class CauseType(models.TextChoices):
    HARDWARE_FAILURE = "hardware_failure", "Hardware failure"
    SOFTWARE_FAULT = "software_fault", "Software fault"
    FORESEEABLE_MISUSE = "foreseeable_misuse", "Foreseeable misuse"
    CYBERATTACK = "cyberattack", "Cyberattack"


class ImpactCategory(models.TextChoices):
    SAFETY = "safety", "Safety (people)"
    PROPERTY_DAMAGE = "property_damage", "Property damage"
    OPERATIONAL = "operational", "Operational"
    FINANCIAL = "financial", "Financial"
    PRIVACY = "privacy", "Privacy"


class CIAProperty(models.TextChoices):
    CONFIDENTIALITY = "confidentiality", "Confidentiality"
    INTEGRITY = "integrity", "Integrity"
    AVAILABILITY = "availability", "Availability"


class RiskEntry(models.Model):
    """One typed entry (asset, threat or hazard) in a product's risk register.

    Cause and consequence are kept separate (see docs/architecture.md,
    "Risk register"): a threat's ``violates`` names how an asset is
    compromised (CIA); its :class:`ThreatConsequence` rows say what
    happens as a result. A hazard's :class:`HazardCause` rows say why it
    might occur.

    Scoping: all three ``scope_*`` fields null means the entry is the
    product baseline (applies to every configuration). Setting one scopes
    it to matching configurations only. A scoped entry with ``base_entry``
    set is a delta overriding that baseline entry for matching
    configurations (see apps/risk/resolution.py).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="risk_entries")
    entry_type = models.CharField(max_length=16, choices=EntryType.choices)
    label = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    # Threats only.
    asset = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="threats",
        help_text="Threats only: the asset this threat targets.",
    )
    violates = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Threats only: the property violated (must be one of the method's properties).",
    )

    # Scoping and deltas.
    scope_hardware_variant = models.ForeignKey(
        HardwareVariant,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="risk_entries",
    )
    scope_software_release = models.ForeignKey(
        SoftwareRelease,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="risk_entries",
    )
    scope_software_option = models.ForeignKey(
        SoftwareOption,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="risk_entries",
    )
    base_entry = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="deltas",
        help_text="If set, this scoped entry overrides that baseline entry for matching "
        "configurations.",
    )
    delta_justification = models.TextField(blank=True, default="")

    # Provenance: suggested from a catalog trigger, or added by hand.
    source_catalog = models.ForeignKey(
        RequirementPackage, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    source_catalog_entry_id = models.CharField(max_length=100, blank=True, default="")
    suggestion_status = models.CharField(
        max_length=16, choices=SuggestionStatus.choices, default=SuggestionStatus.CUSTOM
    )
    dismissal_reason = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["product", "entry_type", "label"]

    def __str__(self):
        return f"{self.get_entry_type_display()}: {self.label}"

    @property
    def is_baseline(self) -> bool:
        return not (
            self.scope_hardware_variant_id
            or self.scope_software_release_id
            or self.scope_software_option_id
        )

    def clean(self):
        scopes = [
            self.scope_hardware_variant_id,
            self.scope_software_release_id,
            self.scope_software_option_id,
        ]
        if sum(bool(s) for s in scopes) > 1:
            raise ValidationError(
                "An entry may be scoped to at most one of hardware variant, "
                "software release or software option."
            )
        if self.entry_type == EntryType.THREAT and not self.violates:
            raise ValidationError({"violates": "Threats must name the property they violate."})
        if self.entry_type != EntryType.THREAT and self.asset_id:
            raise ValidationError({"asset": "Only threats target an asset."})
        if self.base_entry_id and self.is_baseline:
            raise ValidationError("A delta (base_entry set) must itself be scoped.")
        if self.suggestion_status == SuggestionStatus.DISMISSED and not self.dismissal_reason:
            raise ValidationError({"dismissal_reason": "A dismissed suggestion needs a reason."})


class AssetRating(models.Model):
    """Per-property (CIA) severity rating of an asset entry, per method."""

    entry = models.ForeignKey(RiskEntry, on_delete=models.CASCADE, related_name="asset_ratings")
    method = models.ForeignKey(RequirementPackage, on_delete=models.PROTECT, related_name="+")
    property = models.CharField(max_length=32, choices=CIAProperty.choices)
    severity = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "method", "property"], name="unique_asset_rating"
            ),
        ]

    def __str__(self):
        return f"{self.entry.label} {self.property}={self.severity}"


class ThreatConsequence(models.Model):
    """One consequence of a threat, in an impact category with its own severity.

    By default inherits the targeted asset's rating for the violated
    property; an override needs a justification (see
    docs/architecture.md, "Assets and threats").
    """

    threat = models.ForeignKey(RiskEntry, on_delete=models.CASCADE, related_name="consequences")
    impact_category = models.CharField(max_length=32, choices=ImpactCategory.choices)
    severity = models.PositiveSmallIntegerField()
    severity_is_override = models.BooleanField(default=False)
    override_justification = models.TextField(blank=True, default="")
    hazard = models.ForeignKey(
        RiskEntry,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="threat_consequences",
        help_text="Safety/property-damage consequences link to the hazard entry they cause.",
    )

    def __str__(self):
        return f"{self.threat.label} / {self.impact_category}={self.severity}"

    def clean(self):
        if self.severity_is_override and not self.override_justification:
            raise ValidationError(
                {
                    "override_justification": (
                        "An overridden consequence severity needs a justification."
                    )
                }
            )
        if self.hazard_id and self.impact_category not in (
            ImpactCategory.SAFETY,
            ImpactCategory.PROPERTY_DAMAGE,
        ):
            raise ValidationError(
                {"hazard": "Only safety or property-damage consequences link to a hazard."}
            )


class Rating(models.Model):
    """One rating per (threat or hazard entry, method).

    Hazards store severity directly; a threat's severity is derived from
    its worst consequence (see apps/risk/services.py), so only its
    likelihood is stored here.
    """

    entry = models.ForeignKey(RiskEntry, on_delete=models.CASCADE, related_name="ratings")
    method = models.ForeignKey(RequirementPackage, on_delete=models.PROTECT, related_name="+")
    severity = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Hazards only; a threat's severity is derived."
    )
    likelihood = models.PositiveSmallIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entry", "method"], name="unique_rating_per_method"),
        ]

    def __str__(self):
        return f"{self.entry.label} @ {self.method.source} l={self.likelihood}"

    def clean(self):
        if self.entry.entry_type == EntryType.HAZARD and self.severity is None:
            raise ValidationError({"severity": "Hazards must have a directly-rated severity."})
        if self.entry.entry_type == EntryType.THREAT and self.severity is not None:
            raise ValidationError(
                {
                    "severity": (
                        "A threat's severity is derived from its consequences, not stored here."
                    )
                }
            )


class HazardCause(models.Model):
    """One cause of a hazard: hardware failure, software fault, foreseeable
    misuse, or a cyberattack (linking the responsible threat entry)."""

    hazard = models.ForeignKey(RiskEntry, on_delete=models.CASCADE, related_name="causes")
    cause_type = models.CharField(max_length=32, choices=CauseType.choices)
    description = models.TextField(blank=True, default="")
    threat = models.ForeignKey(
        RiskEntry, null=True, blank=True, on_delete=models.SET_NULL, related_name="hazard_causes"
    )

    def __str__(self):
        return f"{self.hazard.label} <- {self.cause_type}"

    def clean(self):
        if self.cause_type == CauseType.CYBERATTACK and not self.threat_id:
            raise ValidationError(
                {"threat": "A cyberattack cause should link the responsible threat entry."}
            )
        if self.cause_type != CauseType.CYBERATTACK and self.threat_id:
            raise ValidationError({"threat": "Only a cyberattack cause links a threat."})


class ControlStatus(models.TextChoices):
    PLANNED = "planned", "Planned"
    IMPLEMENTED = "implemented", "Implemented"
    VERIFIED = "verified", "Verified"


class Control(models.Model):
    """A mitigation, as its own entity from the start so evidence can
    attach to it in a later milestone without a migration."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="controls")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=ControlStatus.choices, default=ControlStatus.PLANNED
    )
    threats = models.ManyToManyField(RiskEntry, related_name="controls", blank=True)
    hazard_causes = models.ManyToManyField(HazardCause, related_name="controls", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    history = HistoricalRecords()

    def __str__(self):
        return self.name


class TreatmentType(models.TextChoices):
    MITIGATE = "mitigate", "Mitigate"
    ACCEPT = "accept", "Accept"
    TRANSFER = "transfer", "Transfer"
    AVOID = "avoid", "Avoid"


class Treatment(models.Model):
    """Treatment decision and residual rating for an entry, per method."""

    entry = models.ForeignKey(RiskEntry, on_delete=models.CASCADE, related_name="treatments")
    method = models.ForeignKey(RequirementPackage, on_delete=models.PROTECT, related_name="+")
    treatment_type = models.CharField(max_length=16, choices=TreatmentType.choices)
    residual_severity = models.PositiveSmallIntegerField(null=True, blank=True)
    residual_likelihood = models.PositiveSmallIntegerField(null=True, blank=True)
    justification = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    history = HistoricalRecords()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entry", "method"], name="unique_treatment_per_method"
            ),
        ]

    def __str__(self):
        return f"{self.entry.label} @ {self.method.source}: {self.treatment_type}"


class RiskAssessmentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"


class RiskAssessment(models.Model):
    """Approval snapshot of a configuration's risk register view.

    Mirrors apps.assessments.Assessment: freezes the resolved register
    (baseline + deltas), ratings, treatments and method/catalog versions
    at approval time; later changes never alter it, only mark it stale.
    """

    configuration = models.ForeignKey(
        Configuration, on_delete=models.PROTECT, related_name="risk_assessments"
    )
    status = models.CharField(
        max_length=16, choices=RiskAssessmentStatus.choices, default=RiskAssessmentStatus.DRAFT
    )
    snapshot = models.JSONField(null=True, blank=True)
    stale = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"RiskAssessment #{self.pk} of {self.configuration} ({self.status})"
