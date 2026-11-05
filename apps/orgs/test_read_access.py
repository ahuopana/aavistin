"""Read access to product-scoped pages: a user with no role on a product must get
a 404 (not a redirect, not the page), whatever the page. A role at any level that
reaches the product — and superusers — can read."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.assessments.models import Assessment
from apps.evidence.models import Evidence, EvidenceKind
from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment
from apps.orgs.services import can_view_product
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareRelease,
)
from apps.risk.models import EntryType, RiskEntry

User = get_user_model()


class ProductReadAccessTests(TestCase):
    def setUp(self):
        self.org = Organisation.objects.create(name="Acme", slug="acme")
        self.family = ProductFamily.objects.create(
            organisation=self.org, name="Sensors", slug="sensors"
        )
        self.product = Product.objects.create(
            product_family=self.family, name="TempSense", slug="tempsense"
        )
        variant = HardwareVariant.objects.create(product=self.product, name="EU", slug="eu")
        revision = HardwareRevision.objects.create(hardware_variant=variant, label="A")
        release = SoftwareRelease.objects.create(product=self.product, version="1.0")
        self.configuration = Configuration.objects.create(
            name="TempSense EU 1.0", hardware_revision=revision, software_release=release
        )
        self.assessment = Assessment.objects.create(configuration=self.configuration)
        self.entry = RiskEntry.objects.create(
            product=self.product, entry_type=EntryType.ASSET, label="Firmware"
        )
        self.evidence = Evidence.objects.create(
            product=self.product,
            title="Policy",
            kind=EvidenceKind.TEXT,
            reference_text="See wiki",
        )
        self.outsider = User.objects.create_user(username="outsider", password="x")

    def urls(self):
        cfg = self.configuration.pk
        return [
            reverse("products:product_detail", args=[self.product.pk]),
            reverse("assessments:configuration_detail", args=[cfg]),
            reverse("assessments:assessment_detail", args=[self.assessment.pk]),
            reverse("risk:register", args=[cfg]),
            reverse("risk:entry_detail", args=[cfg, self.entry.pk]),
            reverse("risk:suggestions", args=[cfg]),
            reverse("evidence:product_list", args=[self.product.pk]),
            reverse("evidence:detail", args=[self.evidence.pk]),
            reverse("evidence:download", args=[self.evidence.pk]),
        ]

    def test_user_without_role_gets_404_everywhere(self):
        self.client.force_login(self.outsider)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_role_on_another_organisation_is_not_enough(self):
        other = Organisation.objects.create(name="Other", slug="other")
        RoleAssignment.objects.create(role=Role.APPROVER, user=self.outsider, organisation=other)
        self.client.force_login(self.outsider)
        for url in self.urls():
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        for url in self.urls():
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("login"), response["Location"])

    def test_viewer_at_each_scope_can_read(self):
        scopes = {
            "organisation": {"organisation": self.org},
            "product_family": {"product_family": self.family},
            "product": {"product": self.product},
        }
        for name, scope in scopes.items():
            user = User.objects.create_user(username=f"viewer-{name}", password="x")
            RoleAssignment.objects.create(role=Role.VIEWER, user=user, **scope)
            self.client.force_login(user)
            for url in self.urls():
                if url.endswith("/download/"):
                    continue  # a text evidence record has no file: 404 for everyone
                with self.subTest(scope=name, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_superuser_can_read(self):
        admin = User.objects.create_superuser(username="root", password="x")
        self.assertTrue(can_view_product(admin, self.product))
        self.client.force_login(admin)
        response = self.client.get(reverse("products:product_detail", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)

    def test_group_grant_can_read(self):
        from django.contrib.auth.models import Group

        group = Group.objects.create(name="auditors")
        self.outsider.groups.add(group)
        RoleAssignment.objects.create(role=Role.VIEWER, group=group, product=self.product)
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("products:product_detail", args=[self.product.pk]))
        self.assertEqual(response.status_code, 200)
