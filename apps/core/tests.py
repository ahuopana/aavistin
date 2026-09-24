import json
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, AssessmentStatus
from apps.core.management.commands.scheduler import SCHEDULE
from apps.core.services import (
    compliance_ratio,
    dashboard_products,
    dashboard_tasks,
    product_tree,
    risk_ratio,
)
from apps.evidence.models import Evidence, EvidenceKind
from apps.evidence.services import link_evidence
from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment
from apps.packages.importer import approve_package, import_package
from apps.packages.models import PackageKind
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareRelease,
    TargetMarket,
)
from apps.risk.models import Control, EntryType, RiskEntry, Treatment

PACKAGES_DIR = Path(settings.BASE_DIR) / "packages"


def load_package(dirname: str, version: str) -> dict:
    with (PACKAGES_DIR / dirname / f"{version}.json").open() as f:
        return json.load(f)


class HomePageTests(TestCase):
    def test_home_page_renders(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "base.html")
        self.assertTemplateUsed(response, "core/home.html")


class DashboardFixture(TestCase):
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
        self.variant.target_markets.add(TargetMarket.objects.get(code="EU"))
        self.revision = HardwareRevision.objects.create(hardware_variant=self.variant, label="A")
        self.release = SoftwareRelease.objects.create(
            product=self.product, name="Firmware", version="1.0"
        )
        self.configuration = Configuration.objects.create(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )

        self.package = import_package(
            load_package("demo-widget-safety", "1.1.0"), is_official=True
        )
        approve_package(self.package)
        self.method = import_package(
            load_package("demo-safety-5x5", "1.0.0"), kind=PackageKind.METHOD, is_official=True
        )
        approve_package(self.method)

        self.editor = User.objects.create_user(username="edna", password="x")
        RoleAssignment.objects.create(role=Role.EDITOR, user=self.editor, product=self.product)
        self.viewer = User.objects.create_user(username="vera", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.viewer, product=self.product)
        self.outsider = User.objects.create_user(username="oscar", password="x")

    def _ready_answers(self, has_wireless=False):
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=20, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)
        Answer.objects.create(
            question_id="has_wireless", value=has_wireless, hardware_revision=self.revision
        )


class ComplianceRatioTests(DashboardFixture):
    def test_no_configurations_returns_zero_over_zero(self):
        empty_product = Product.objects.create(
            product_family=self.family, name="Empty", slug="empty"
        )
        self.assertEqual(compliance_ratio(empty_product), (0, 0))

    def test_no_action_required_finding_is_fully_compliant(self):
        self._ready_answers(has_wireless=False)
        self.assertEqual(compliance_ratio(self.product), (2, 2))

    def test_action_required_finding_marks_its_package_requirements_bad(self):
        self._ready_answers(has_wireless=True)
        self.assertEqual(compliance_ratio(self.product), (0, 2))


class RiskRatioTests(DashboardFixture):
    def _make_threat(self, **kwargs):
        asset = RiskEntry.objects.create(
            product=self.product, entry_type=EntryType.ASSET, label="Firmware"
        )
        return RiskEntry.objects.create(
            product=self.product,
            entry_type=EntryType.THREAT,
            label="Eavesdropping",
            asset=asset,
            violates="confidentiality",
            **kwargs,
        )

    def test_no_entries_returns_zero_over_zero(self):
        self.assertEqual(risk_ratio(self.product), (0, 0))

    def test_untreated_entry_is_not_acceptable(self):
        self._make_threat()
        self.assertEqual(risk_ratio(self.product), (0, 1))

    def test_accepted_residual_is_acceptable(self):
        threat = self._make_threat()
        Treatment.objects.create(
            entry=threat,
            method=self.method,
            treatment_type="mitigate",
            residual_severity=1,
            residual_likelihood=1,
        )
        self.assertEqual(risk_ratio(self.product), (1, 1))

    def test_must_treat_residual_is_not_acceptable(self):
        threat = self._make_threat()
        Treatment.objects.create(
            entry=threat,
            method=self.method,
            treatment_type="mitigate",
            residual_severity=5,
            residual_likelihood=5,
        )
        self.assertEqual(risk_ratio(self.product), (0, 1))

    def test_scoped_entry_excluded_from_baseline_count(self):
        self._make_threat(scope_software_release=self.release)
        self.assertEqual(risk_ratio(self.product), (0, 0))

    def test_asset_entries_excluded(self):
        RiskEntry.objects.create(
            product=self.product, entry_type=EntryType.ASSET, label="Firmware only"
        )
        self.assertEqual(risk_ratio(self.product), (0, 0))


class DashboardProductsTests(DashboardFixture):
    def test_no_products_for_outsider(self):
        self.assertEqual(dashboard_products(self.outsider), [])

    def test_viewer_sees_product_with_ratios(self):
        self._ready_answers(has_wireless=False)
        rows = dashboard_products(self.viewer)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["product"], self.product)
        self.assertEqual(rows[0]["compliance"], (2, 2))

    def test_editor_only_user_also_sees_product_widget(self):
        # Roles aren't tiered: an Editor grant doesn't imply Viewer, so
        # this must not depend on role=Role.VIEWER specifically.
        rows = dashboard_products(self.editor)
        self.assertEqual([r["product"] for r in rows], [self.product])

    def test_limit_caps_results(self):
        for i in range(5):
            product = Product.objects.create(
                product_family=self.family, name=f"Product {i}", slug=f"product-{i}"
            )
            RoleAssignment.objects.create(role=Role.VIEWER, user=self.viewer, product=product)
        rows = dashboard_products(self.viewer, limit=3)
        self.assertEqual(len(rows), 3)


class DashboardTasksTests(DashboardFixture):
    def test_viewer_gets_no_tasks(self):
        self.assertEqual(dashboard_tasks(self.viewer), [])

    def test_configuration_without_assessment_suggests_starting_one(self):
        tasks = dashboard_tasks(self.editor)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["kind"], "start_assessment")

    def test_draft_assessment_suggests_completing_it(self):
        Assessment.objects.create(configuration=self.configuration)
        tasks = dashboard_tasks(self.editor)
        self.assertEqual([t["kind"] for t in tasks], ["complete_assessment"])

    def test_stale_approved_assessment_suggests_review(self):
        self._ready_answers(has_wireless=False)
        assessment = Assessment.objects.create(
            configuration=self.configuration,
            status=AssessmentStatus.APPROVED,
            snapshot={"resolved_answers": {}, "results": [], "findings": [], "packages": []},
            stale=True,
        )
        tasks = dashboard_tasks(self.editor)
        self.assertIn("stale_assessment", [t["kind"] for t in tasks])
        self.assertTrue(any(str(assessment.pk) in t["url"] for t in tasks))

    def test_control_without_evidence_suggests_providing_it(self):
        Assessment.objects.create(
            configuration=self.configuration,
            status=AssessmentStatus.APPROVED,
            snapshot={"resolved_answers": {}, "results": [], "findings": [], "packages": []},
        )
        Control.objects.create(product=self.product, name="Secure boot")
        tasks = dashboard_tasks(self.editor)
        self.assertIn("provide_evidence", [t["kind"] for t in tasks])

    def test_control_with_evidence_excluded(self):
        Assessment.objects.create(
            configuration=self.configuration,
            status=AssessmentStatus.APPROVED,
            snapshot={"resolved_answers": {}, "results": [], "findings": [], "packages": []},
        )
        control = Control.objects.create(product=self.product, name="Secure boot")
        evidence = Evidence.objects.create(
            product=self.product,
            title="Secure boot design doc",
            kind=EvidenceKind.TEXT,
            reference_text="see wiki",
        )
        link_evidence(evidence, control=control)
        tasks = dashboard_tasks(self.editor)
        self.assertNotIn("provide_evidence", [t["kind"] for t in tasks])

    def test_limit_caps_and_varies_across_kinds(self):
        Assessment.objects.create(
            configuration=self.configuration,
            status=AssessmentStatus.APPROVED,
            snapshot={"resolved_answers": {}, "results": [], "findings": [], "packages": []},
        )
        for i in range(3):
            Control.objects.create(product=self.product, name=f"Control {i}")
        other_release = SoftwareRelease.objects.create(
            product=self.product, name="Firmware", version="2.0"
        )
        other_config = Configuration.objects.create(
            name="TempSense EU 2.0",
            hardware_revision=self.revision,
            software_release=other_release,
        )
        self.assertIsNotNone(other_config.pk)
        tasks = dashboard_tasks(self.editor, limit=3)
        self.assertEqual(len(tasks), 3)
        kinds = {t["kind"] for t in tasks}
        self.assertIn("start_assessment", kinds)
        self.assertIn("provide_evidence", kinds)


class ProductTreeTests(DashboardFixture):
    def test_outsider_sees_empty_tree(self):
        self.assertEqual(product_tree(self.outsider), [])

    def test_tree_has_organisation_family_product_and_revision(self):
        tree = product_tree(self.viewer)
        self.assertEqual(len(tree), 1)
        org_node = tree[0]
        self.assertEqual(org_node["organisation"], self.org)
        self.assertEqual(len(org_node["families"]), 1)
        family_node = org_node["families"][0]
        self.assertEqual(family_node["family"], self.family)
        self.assertEqual(len(family_node["products"]), 1)
        row = family_node["products"][0]
        self.assertEqual(row["product"], self.product)
        self.assertEqual(row["revisions"], ["EU variant rev A"])
        self.assertEqual(row["releases"], ["Firmware 1.0"])

    def test_multiple_products_grouped_under_same_family(self):
        other_product = Product.objects.create(
            product_family=self.family, name="OtherWidget", slug="other-widget"
        )
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.viewer, product=other_product)
        tree = product_tree(self.viewer)
        family_node = tree[0]["families"][0]
        self.assertEqual(len(family_node["products"]), 2)


class DashboardViewTests(DashboardFixture):
    def test_authenticated_user_sees_dashboard_template(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/dashboard.html")

    def test_outsider_sees_empty_state_cta(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "add one")


class SchedulerCommandTests(TestCase):
    def test_once_enqueues_every_scheduled_task(self):
        # Under the immediate backend forced by conftest.py, .enqueue()
        # runs synchronously in-process rather than writing a DBTaskResult
        # row — so this only checks the command reports one "Enqueued"
        # line per scheduled task, not the (DatabaseBackend-only) storage.
        # The real DatabaseBackend + db_worker path is exercised manually
        # (see docs/adr/0007-background-job-backend.md); a TransactionTestCase
        # version of this was tried and dropped — it left the shared test
        # database missing migration-seeded rows for later tests when reused
        # across runs (pytest's --reuse-db), which isn't worth the flakiness
        # for what it additionally proves.
        out = StringIO()
        call_command("scheduler", "--once", stdout=out)
        self.assertEqual(out.getvalue().count("Enqueued"), len(SCHEDULE))
