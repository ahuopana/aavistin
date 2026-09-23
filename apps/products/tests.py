from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment

from .models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareOption,
    SoftwareRelease,
    TargetMarket,
)
from .services import (
    ApprovedEntityError,
    approve,
    delete_entity,
    editable_product_families,
    editable_products,
    product_of,
)

User = get_user_model()


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


class ProductAuthoringFixture(TestCase):
    """One product hierarchy plus editor/approver/viewer users, RoleAssignment'd
    at product_family scope — mirrors apps.assessments.tests.ConfigurationFixture."""

    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.product = Product.objects.create(
            product_family=self.family, name="TempSense", slug="tempsense"
        )
        self.variant = HardwareVariant.objects.create(
            product=self.product, name="EU variant", slug="eu-variant"
        )
        self.revision = HardwareRevision.objects.create(hardware_variant=self.variant, label="A")
        self.release = SoftwareRelease.objects.create(product=self.product, version="1.0")
        self.option = SoftwareOption.objects.create(
            software_release=self.release, name="Bluetooth", slug="bluetooth"
        )
        self.configuration = Configuration.objects.create(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )

        self.editor = User.objects.create_user(username="edna", password="x")
        self.approver = User.objects.create_user(username="ana", password="x")
        self.viewer = User.objects.create_user(username="vera", password="x")
        RoleAssignment.objects.create(
            role=Role.EDITOR, user=self.editor, product_family=self.family
        )
        RoleAssignment.objects.create(
            role=Role.APPROVER, user=self.approver, product_family=self.family
        )
        RoleAssignment.objects.create(
            role=Role.VIEWER, user=self.viewer, product_family=self.family
        )


class ApprovableServiceTests(ProductAuthoringFixture):
    def test_product_of_resolves_every_level(self):
        self.assertEqual(product_of(self.product), self.product)
        self.assertEqual(product_of(self.variant), self.product)
        self.assertEqual(product_of(self.revision), self.product)
        self.assertEqual(product_of(self.release), self.product)
        self.assertEqual(product_of(self.option), self.product)
        self.assertEqual(product_of(self.configuration), self.product)

    def test_product_of_rejects_unknown_type(self):
        with self.assertRaises(TypeError):
            product_of(self.org)

    def test_approve_sets_fields(self):
        approve(self.product, actor=self.approver)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_approved)
        self.assertEqual(self.product.approved_by, self.approver)
        self.assertIsNotNone(self.product.approved_at)

    def test_delete_entity_allowed_when_unapproved(self):
        delete_entity(self.option)
        self.assertFalse(SoftwareOption.objects.filter(pk=self.option.pk).exists())

    def test_delete_entity_blocked_when_approved(self):
        approve(self.option, actor=self.approver)
        with self.assertRaises(ApprovedEntityError):
            delete_entity(self.option)
        self.assertTrue(SoftwareOption.objects.filter(pk=self.option.pk).exists())

    def test_approved_entity_can_still_be_modified(self):
        approve(self.product, actor=self.approver)
        self.product.refresh_from_db()
        self.product.description = "updated after approval"
        self.product.full_clean()
        self.product.save()
        self.product.refresh_from_db()
        self.assertEqual(self.product.description, "updated after approval")
        self.assertTrue(self.product.is_approved)


class EditableScopeTests(ProductAuthoringFixture):
    def test_family_scoped_grant_is_editable(self):
        self.assertIn(self.family, editable_product_families(self.editor))
        self.assertIn(self.product, editable_products(self.editor))

    def test_org_scoped_grant_covers_all_families(self):
        org_editor = User.objects.create_user(username="oscar", password="x")
        RoleAssignment.objects.create(role=Role.EDITOR, user=org_editor, organisation=self.org)
        self.assertIn(self.family, editable_product_families(org_editor))
        self.assertIn(self.product, editable_products(org_editor))

    def test_product_scoped_grant_is_narrow(self):
        other_product = Product.objects.create(
            product_family=self.family, name="HumSense", slug="humsense"
        )
        narrow_editor = User.objects.create_user(username="nora", password="x")
        RoleAssignment.objects.create(role=Role.EDITOR, user=narrow_editor, product=self.product)
        editable = editable_products(narrow_editor)
        self.assertIn(self.product, editable)
        self.assertNotIn(other_product, editable)
        # No family-level grant, so the family-level listing stays empty for this user.
        self.assertNotIn(self.family, editable_product_families(narrow_editor))

    def test_viewer_role_is_not_editor_scoped(self):
        self.assertNotIn(self.product, editable_products(self.viewer))

    def test_superuser_sees_everything(self):
        superuser = User.objects.create_superuser(username="root", password="x")
        self.assertIn(self.product, editable_products(superuser))
        self.assertIn(self.family, editable_product_families(superuser))

    def test_anonymous_sees_nothing(self):
        from django.contrib.auth.models import AnonymousUser

        anon = AnonymousUser()
        self.assertEqual(editable_products(anon).count(), 0)
        self.assertEqual(editable_product_families(anon).count(), 0)

    def test_role_none_matches_any_role(self):
        # Roles aren't tiered -- an Editor grant is not also a Viewer
        # grant -- so role=None (any role at all) must see the product
        # via editor.editor, approver.approver AND viewer.viewer alike.
        self.assertIn(self.product, editable_products(self.editor, role=None))
        self.assertIn(self.product, editable_products(self.approver, role=None))
        self.assertIn(self.product, editable_products(self.viewer, role=None))
        self.assertIn(self.family, editable_product_families(self.editor, role=None))


class ProductViewTests(ProductAuthoringFixture):
    def test_product_detail_requires_login(self):
        response = self.client.get(reverse("products:product_detail", args=[self.product.pk]))
        self.assertEqual(response.status_code, 302)

    def test_product_detail_shows_permission_flags(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("products:product_detail", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_edit"])
        self.assertFalse(response.context["can_approve"])

    def test_editor_can_create_product(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("products:product_create", args=[self.family.pk]),
            {"name": "New Product", "slug": "new-product"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Product.objects.filter(slug="new-product").exists())

    def test_viewer_cannot_create_product(self):
        self.client.force_login(self.viewer)
        self.client.post(
            reverse("products:product_create", args=[self.family.pk]),
            {"name": "New Product", "slug": "new-product"},
        )
        self.assertFalse(Product.objects.filter(slug="new-product").exists())

    def test_editor_can_create_hardware_variant(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("products:hardware_variant_create", args=[self.product.pk]),
            {"name": "US variant", "slug": "us-variant"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(HardwareVariant.objects.filter(slug="us-variant").exists())

    def test_editor_can_create_hardware_revision(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("products:hardware_revision_create", args=[self.variant.pk]),
            {"label": "B"},
        )
        self.assertTrue(
            HardwareRevision.objects.filter(hardware_variant=self.variant, label="B").exists()
        )

    def test_editor_can_create_software_release(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("products:software_release_create", args=[self.product.pk]),
            {"version": "2.0"},
        )
        self.assertTrue(
            SoftwareRelease.objects.filter(product=self.product, version="2.0").exists()
        )

    def test_editor_can_create_software_option(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("products:software_option_create", args=[self.release.pk]),
            {"name": "WiFi", "slug": "wifi"},
        )
        self.assertTrue(SoftwareOption.objects.filter(slug="wifi").exists())

    def test_editor_can_create_configuration_with_options(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("products:configuration_create", args=[self.product.pk]),
            {
                "name": "TempSense EU 2.0",
                "hardware_revision": self.revision.pk,
                "software_release": self.release.pk,
                "software_options": [self.option.pk],
            },
        )
        self.assertEqual(response.status_code, 302)
        config = Configuration.objects.get(name="TempSense EU 2.0")
        self.assertEqual(list(config.software_options.all()), [self.option])

    def test_configuration_create_rejects_mismatched_hardware(self):
        other_variant = HardwareVariant.objects.create(
            product=Product.objects.create(product_family=self.family, name="Other", slug="other"),
            name="Other variant",
            slug="other-variant",
        )
        other_revision = HardwareRevision.objects.create(hardware_variant=other_variant, label="A")
        self.client.force_login(self.editor)
        self.client.post(
            reverse("products:configuration_create", args=[self.product.pk]),
            {
                "name": "Bad config",
                "hardware_revision": other_revision.pk,
                "software_release": self.release.pk,
            },
        )
        self.assertFalse(Configuration.objects.filter(name="Bad config").exists())

    def test_approver_can_approve(self):
        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("products:entity_approve", args=["product", self.product.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.product.refresh_from_db()
        self.assertTrue(self.product.is_approved)

    def test_editor_cannot_approve(self):
        self.client.force_login(self.editor)
        self.client.post(reverse("products:entity_approve", args=["product", self.product.pk]))
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_approved)

    def test_editor_can_delete_unapproved_entity(self):
        self.client.force_login(self.editor)
        self.client.post(
            reverse("products:entity_delete", args=["software-option", self.option.pk])
        )
        self.assertFalse(SoftwareOption.objects.filter(pk=self.option.pk).exists())

    def test_delete_blocked_once_approved(self):
        approve(self.option, actor=self.approver)
        self.client.force_login(self.editor)
        self.client.post(
            reverse("products:entity_delete", args=["software-option", self.option.pk])
        )
        self.assertTrue(SoftwareOption.objects.filter(pk=self.option.pk).exists())


class SeedDevRolesCommandTests(TestCase):
    def test_creates_groups_org_family_and_role_assignments(self):
        call_command("seed_dev_roles")

        self.assertEqual(Group.objects.filter(name="Editor").count(), 1)
        self.assertEqual(Group.objects.filter(name="Approver").count(), 1)
        self.assertEqual(Group.objects.count(), 5)

        org = Organisation.objects.get(slug="default")
        family = ProductFamily.objects.get(organisation=org, slug="default")
        self.assertTrue(
            RoleAssignment.objects.filter(
                group__name="Editor", role=Role.EDITOR, organisation=org
            ).exists()
        )
        self.assertTrue(
            RoleAssignment.objects.filter(
                group__name="Approver", role=Role.APPROVER, organisation=org
            ).exists()
        )
        self.assertIsNotNone(family)

    def test_grants_dev_user_when_present(self):
        User.objects.create_user(username="aavistin", password="aavistin")
        call_command("seed_dev_roles")
        dev_user = User.objects.get(username="aavistin")
        group_names = set(dev_user.groups.values_list("name", flat=True))
        self.assertEqual(group_names, {"Editor", "Approver"})

    def test_warns_but_does_not_fail_when_dev_user_missing(self):
        call_command("seed_dev_roles")
        self.assertFalse(User.objects.filter(username="aavistin").exists())

    def test_idempotent(self):
        User.objects.create_user(username="aavistin", password="aavistin")
        call_command("seed_dev_roles")
        call_command("seed_dev_roles")
        self.assertEqual(Group.objects.filter(name="Editor").count(), 1)
        self.assertEqual(Organisation.objects.filter(slug="default").count(), 1)
        self.assertEqual(
            RoleAssignment.objects.filter(role=Role.EDITOR, organisation__slug="default").count(),
            1,
        )
