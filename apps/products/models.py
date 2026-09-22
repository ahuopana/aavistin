from django.core.exceptions import ValidationError
from django.db import models

from apps.orgs.models import ProductFamily


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


class Product(models.Model):
    product_family = models.ForeignKey(
        ProductFamily, on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField(blank=True, default="")
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


class HardwareVariant(models.Model):
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


class HardwareRevision(models.Model):
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


class SoftwareRelease(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="sw_releases")
    version = models.CharField(max_length=50)
    released_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["product__name", "version"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "version"], name="unique_sw_release_version_per_product"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} {self.version}"


class SoftwareOption(models.Model):
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


class Configuration(models.Model):
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
