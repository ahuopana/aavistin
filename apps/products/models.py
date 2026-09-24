from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.orgs.models import ProductFamily


class Approvable(models.Model):
    """Shared approval state for Product and everything beneath it.

    See docs/adr/0008-product-level-authoring-and-approval-deferred.md:
    approval only blocks *deletion* (apps.products.services.delete_entity);
    an approved entity may still be freely modified.
    """

    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        abstract = True


class ProductStatus(models.TextChoices):
    """Product lifecycle stage, independent of the per-entity Approvable bits.

    Draft -> Approved -> Closed is the forward path (Closed meaning e.g.
    "CE marked", though nothing here enforces that a risk assessment
    approval exists yet -- that link is future work). Archived and
    Deleted are side branches: Archived is a reversible "not active right
    now", Deleted is a soft delete (hidden from listings, not removed
    from the database) so approved/historical products are never
    actually destroyed by this UI.
    """

    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"
    CLOSED = "closed", "Closed"
    ARCHIVED = "archived", "Archived"
    DELETED = "deleted", "Deleted"


class TargetMarket(models.Model):
    """A jurisdiction a hardware variant can be sold into (EU, US, UK, ...).

    Reference data only — no regulation scope or requirements live here.
    The code is matched against a requirement package's ``jurisdiction``
    (Milestone 4) to decide which packages apply.
    """

    code = models.CharField(max_length=16, unique=True, help_text="e.g. EU, US, UK")
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Product(Approvable):
    product_family = models.ForeignKey(
        ProductFamily, on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=ProductStatus.choices, default=ProductStatus.DRAFT
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product_family__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["product_family", "slug"], name="unique_product_slug_per_family"
            ),
        ]

    def __str__(self):
        return self.name


class HardwareVariant(Approvable):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="hw_variants")
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    target_markets = models.ManyToManyField(TargetMarket, related_name="hw_variants", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "slug"], name="unique_hw_variant_slug_per_product"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} / {self.name}"


class HardwareRevision(Approvable):
    hardware_variant = models.ForeignKey(
        HardwareVariant, on_delete=models.CASCADE, related_name="revisions"
    )
    label = models.CharField(max_length=50, help_text="e.g. A, B, Rev2")
    released_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["hardware_variant", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["hardware_variant", "label"], name="unique_hw_revision_label"
            ),
        ]

    def __str__(self):
        return f"{self.hardware_variant} rev {self.label}"


class SoftwareRelease(Approvable):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sw_releases")
    name = models.CharField(max_length=200, help_text="e.g. Firmware, Companion app")
    version = models.CharField(max_length=50)
    released_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product__name", "name", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "name", "version"], name="unique_sw_release_version_per_product"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} {self.name} {self.version}"


class SoftwareOption(Approvable):
    software_release = models.ForeignKey(
        SoftwareRelease, on_delete=models.CASCADE, related_name="options"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["software_release", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["software_release", "slug"], name="unique_sw_option_slug_per_release"
            ),
        ]

    def __str__(self):
        return f"{self.software_release} / {self.name}"


class Configuration(Approvable):
    """One shipped combination: a HW revision, a SW release and its selected options.

    Only configurations actually shipped are defined here, to avoid
    assessing every possible combination (see docs/architecture.md,
    "Products and assessments").
    """

    name = models.CharField(max_length=200)
    hardware_revision = models.ForeignKey(
        HardwareRevision, on_delete=models.PROTECT, related_name="configurations"
    )
    software_release = models.ForeignKey(
        SoftwareRelease, on_delete=models.PROTECT, related_name="configurations"
    )
    software_options = models.ManyToManyField(
        SoftwareOption, related_name="configurations", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name

    def clean(self):
        hw_product = self.hardware_revision.hardware_variant.product_id
        sw_product = self.software_release.product_id
        if hw_product != sw_product:
            raise ValidationError(
                "The hardware revision and software release must belong to the same product."
            )

    def clean_software_options(self, options):
        """Validate that ``options`` all belong to this configuration's software release.

        Call explicitly after setting software_options (e.g. in a form's
        clean(), or right after .set()), since M2M state isn't available
        during Model.clean() before the instance has a primary key.
        """
        release_id = self.software_release_id
        bad = [o for o in options if o.software_release_id != release_id]
        if bad:
            raise ValidationError(
                "All software options must belong to the configuration's software release."
            )
