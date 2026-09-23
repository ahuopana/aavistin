from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.orgs.models import Organisation, ProductFamily

from .models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareOption,
    SoftwareRelease,
    TargetMarket,
)


class ProductHierarchyTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.product = Product.objects.create(
            product_family=self.family, name="TempSense", slug="tempsense"
        )

    def test_target_markets_seeded_by_migration(self):
        self.assertEqual(TargetMarket.objects.filter(code="EU").count(), 1)
        self.assertEqual(TargetMarket.objects.filter(code="US").count(), 1)

    def test_hardware_variant_can_select_target_markets(self):
        eu = TargetMarket.objects.get(code="EU")
        variant = HardwareVariant.objects.create(
            product=self.product, name="EU variant", slug="eu-variant"
        )
        variant.target_markets.add(eu)
        self.assertEqual(list(variant.target_markets.all()), [eu])

    def test_slug_unique_per_product_not_globally(self):
        other_product = Product.objects.create(
            product_family=self.family, name="HumSense", slug="humsense"
        )
        HardwareVariant.objects.create(product=self.product, name="V1", slug="v1")
        # Same slug on a different product is fine.
        HardwareVariant.objects.create(product=other_product, name="V1", slug="v1")
        self.assertEqual(HardwareVariant.objects.filter(slug="v1").count(), 2)


class ConfigurationTests(TestCase):
    def setUp(self):
        org = Organisation.objects.create(name="Acme", slug="acme")
        family = ProductFamily.objects.create(organisation=org, name="Sensors", slug="sensors")
        self.product = Product.objects.create(
            product_family=family, name="TempSense", slug="tempsense"
        )
        self.other_product = Product.objects.create(
            product_family=family, name="HumSense", slug="humsense"
        )
        variant = HardwareVariant.objects.create(
            product=self.product, name="EU variant", slug="eu-variant"
        )
        self.revision = HardwareRevision.objects.create(hardware_variant=variant, label="A")
        self.release = SoftwareRelease.objects.create(product=self.product, version="1.0")
        self.option = SoftwareOption.objects.create(
            software_release=self.release, name="Bluetooth", slug="bluetooth"
        )
        other_variant = HardwareVariant.objects.create(
            product=self.other_product, name="Base", slug="base"
        )
        self.other_revision = HardwareRevision.objects.create(
            hardware_variant=other_variant, label="A"
        )

    def test_valid_configuration(self):
        config = Configuration(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )
        config.full_clean()
        config.save()
        config.software_options.set([self.option])
        config.clean_software_options(config.software_options.all())

    def test_hardware_and_software_must_share_product(self):
        config = Configuration(
            name="Mismatched",
            hardware_revision=self.other_revision,
            software_release=self.release,
        )
        with self.assertRaises(ValidationError):
            config.clean()

    def test_software_option_must_belong_to_release(self):
        other_release = SoftwareRelease.objects.create(product=self.product, version="2.0")
        other_option = SoftwareOption.objects.create(
            software_release=other_release, name="WiFi", slug="wifi"
        )
        config = Configuration.objects.create(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )
        with self.assertRaises(ValidationError):
            config.clean_software_options([other_option])
