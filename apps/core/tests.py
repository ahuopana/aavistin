import json
import re
from collections import defaultdict
from io import StringIO
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Answer, Assessment, AssessmentStatus
from apps.core.management.commands.scheduler import SCHEDULE
from apps.core.services import (
    compliance_overview,
    dashboard_products,
    dashboard_tasks,
    product_tree,
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
from apps.risk.models import Control

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


class ComplianceOverviewTests(DashboardFixture):
    def test_outsider_sees_no_rows(self):
        overview = compliance_overview(self.outsider)
        self.assertEqual(overview["rows"], [])
        self.assertEqual(
            overview["totals"], {"questions": (0, 0), "compliance": (0, 0), "risk": (0, 0)}
        )

    def test_viewer_sees_product_with_ratios_and_totals(self):
        self._ready_answers(has_wireless=False)
        overview = compliance_overview(self.viewer)
        self.assertEqual(len(overview["rows"]), 1)
        row = overview["rows"][0]
        self.assertEqual(row["product"], self.product)
        self.assertEqual(row["organisation"], self.org)
        self.assertEqual(row["family"], self.family)
        self.assertEqual(row["compliance"], (2, 2))
        self.assertEqual(overview["totals"]["compliance"], (2, 2))
        done, total = row["questions"]
        self.assertEqual(done, total)
        self.assertGreater(total, 0)
        self.assertEqual(overview["totals"]["questions"], row["questions"])

    def test_worst_compliance_sorts_first(self):
        self._ready_answers(has_wireless=True)  # (0, 2) -- fails compliance
        clean_product = Product.objects.create(
            product_family=self.family, name="CleanWidget", slug="clean-widget"
        )
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.viewer, product=clean_product)

        overview = compliance_overview(self.viewer)
        # The product with no data yet sorts as fully clean (fraction 1.0),
        # so the failing product (0/2) must come first.
        self.assertEqual(overview["rows"][0]["product"], self.product)
        self.assertEqual(overview["rows"][1]["product"], clean_product)
        self.assertEqual(overview["rows"][0]["action_required"], 1)
        self.assertEqual(overview["rows"][1]["action_required"], 0)


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


class ComplianceViewTests(DashboardFixture):
    def test_requires_login(self):
        response = self.client.get(reverse("core:compliance"))
        self.assertEqual(response.status_code, 302)

    def test_viewer_sees_compliance_template_and_product(self):
        self._ready_answers(has_wireless=True)
        self.client.force_login(self.viewer)
        response = self.client.get(reverse("core:compliance"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/compliance.html")
        self.assertContains(response, self.product.name)
        self.assertContains(response, "Action required</th>")
        self.assertContains(
            response, reverse("products:product_compliance", args=[self.product.pk])
        )

    def test_outsider_sees_empty_state_cta(self):
        self.client.force_login(self.outsider)
        response = self.client.get(reverse("core:compliance"))
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


class AdrNumberingTests(SimpleTestCase):
    """docs/adr/NNNN-title.md: one number per ADR, and the heading agrees.

    KNOWN_DUPLICATES lists numbers reused before this check existed; their
    files are referenced from elsewhere, so they are allowed rather than
    renumbered. Don't add to it: give a new ADR the next free number.
    """

    ADR_DIR = Path(settings.BASE_DIR) / "docs" / "adr"
    NAME = re.compile(r"^(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
    KNOWN_DUPLICATES = {
        "0015": {"0015-shared-question-library.md", "0015-ui-component-conventions.md"},
    }

    def _adrs(self):
        return sorted(p.name for p in self.ADR_DIR.glob("*.md"))

    def test_file_names_are_numbered(self):
        bad = [name for name in self._adrs() if not self.NAME.match(name)]
        self.assertEqual(bad, [], "ADR files must be named NNNN-lowercase-title.md")

    def test_numbers_are_unique(self):
        by_number = defaultdict(set)
        for name in self._adrs():
            match = self.NAME.match(name)
            if match:
                by_number[match.group(1)].add(name)
        duplicates = {
            number: names
            for number, names in by_number.items()
            if len(names) > 1 and names != self.KNOWN_DUPLICATES.get(number)
        }
        self.assertEqual(duplicates, {}, "Give each new ADR the next free number.")

    def test_heading_matches_file_number(self):
        mismatched = []
        for name in self._adrs():
            match = self.NAME.match(name)
            if not match:
                continue
            first_line = (self.ADR_DIR / name).read_text().splitlines()[0]
            if not first_line.startswith(f"# {int(match.group(1))}. "):
                mismatched.append(f"{name}: {first_line}")
        self.assertEqual(mismatched, [], "An ADR's heading starts with '# <its number>. '")


class NavigationFixture(DashboardFixture):
    def setUp(self):
        super().setUp()
        self.approver = User.objects.create_user(username="ana", password="x")
        RoleAssignment.objects.create(role=Role.APPROVER, user=self.approver, product=self.product)
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.approver, product=self.product)
        RoleAssignment.objects.create(role=Role.VIEWER, user=self.editor, product=self.product)

    def _asset(self):
        from apps.risk.models import EntryType, RiskEntry

        return RiskEntry.objects.create(
            product=self.product, entry_type=EntryType.ASSET, label="Firmware"
        )


class BreadcrumbTests(NavigationFixture):
    def test_trail_from_portfolio_to_current_page(self):
        from apps.core.navigation import breadcrumbs

        crumbs = breadcrumbs(configuration=self.configuration, trail=[("Risk register", None)])
        self.assertEqual(
            [c["label"] for c in crumbs],
            ["Portfolio", "Acme", "Sensors", "TempSense", "TempSense EU 1.0", "Risk register"],
        )
        self.assertEqual(crumbs[2]["url"], reverse("orgs:portfolio") + f"#family-{self.family.pk}")
        self.assertIsNone(crumbs[-1]["url"])
        self.assertIsNotNone(crumbs[-2]["url"])

    def test_pages_below_the_product_link_back_to_it(self):
        self.client.force_login(self.editor)
        product_url = reverse("products:product_detail", args=[self.product.pk])
        assessment = Assessment.objects.create(configuration=self.configuration)
        for url in (
            reverse("assessments:configuration_detail", args=[self.configuration.pk]),
            reverse("assessments:assessment_detail", args=[assessment.pk]),
            reverse("risk:register", args=[self.configuration.pk]),
            reverse("risk:suggestions", args=[self.configuration.pk]),
            reverse("risk:entry_create", args=[self.configuration.pk]),
            reverse("evidence:product_list", args=[self.product.pk]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, 'class="breadcrumb"')
                self.assertContains(response, f'href="{product_url}"')


class WorkflowTests(NavigationFixture):
    def _workflow(self, user):
        from apps.core.navigation import configuration_workflow

        return configuration_workflow(self.configuration, user)

    def test_editor_is_sent_to_open_questions_first(self):
        workflow = self._workflow(self.editor)
        self.assertEqual(workflow["next"]["step"], "questions")
        self.assertIn("?show=open#questions", workflow["next"]["url"])
        self.assertEqual(workflow["steps"][0]["state_class"], "current")

    def test_answered_questions_lead_to_starting_the_assessment(self):
        self._ready_answers()
        workflow = self._workflow(self.editor)
        self.assertEqual(workflow["next"]["step"], "assessment")
        self.assertEqual(
            workflow["next"]["post_url"],
            reverse("assessments:assessment_create", args=[self.configuration.pk]),
        )
        self.assertEqual(workflow["steps"][0]["state_class"], "done")

    def test_approver_waits_while_editors_work_then_approves(self):
        self._ready_answers()
        self.assertTrue(self._workflow(self.approver)["next"]["waiting"])
        Assessment.objects.create(configuration=self.configuration)
        self._asset()
        workflow = self._workflow(self.approver)
        self.assertEqual(workflow["next"]["label"], "Review and approve the assessment")
        self.assertTrue(workflow["next"]["url"].endswith("#approve"))

    def test_everything_approved_completes_the_workflow(self):
        from apps.risk.approval import approve_risk_assessment
        from apps.risk.models import RiskAssessment

        self._ready_answers()
        self._asset()
        Assessment.objects.create(
            configuration=self.configuration, status=AssessmentStatus.APPROVED
        )
        approve_risk_assessment(RiskAssessment.objects.create(configuration=self.configuration))
        workflow = self._workflow(self.approver)
        self.assertEqual(workflow["next"]["label"], "Approve the configuration")
        self.configuration.is_approved = True
        self.configuration.save()
        workflow = self._workflow(self.approver)
        self.assertTrue(workflow["next"]["done"])
        self.assertTrue(all(s["state_class"] == "done" for s in workflow["steps"]))

    def test_stale_assessment_leads_to_a_new_assessment_not_approval(self):
        from apps.core.navigation import approval_items

        self._ready_answers()
        self._asset()
        Assessment.objects.create(
            configuration=self.configuration, status=AssessmentStatus.APPROVED, stale=True
        )
        workflow = self._workflow(self.editor)
        self.assertEqual(workflow["next"]["label"], "Start a new assessment to re-review")
        self.assertEqual(
            workflow["next"]["post_url"],
            reverse("assessments:assessment_create", args=[self.configuration.pk]),
        )
        self.assertTrue(self._workflow(self.approver)["next"]["waiting"])
        kinds = [i["kind"] for g in approval_items(self.approver) for i in g["items"]]
        self.assertNotIn("Assessment", kinds)

    def test_workflow_bar_and_chips_render(self):
        self.client.force_login(self.editor)
        response = self.client.get(
            reverse("assessments:configuration_detail", args=[self.configuration.pk])
        )
        self.assertContains(response, 'class="workflow"')
        self.assertContains(response, "Next step:")
        response = self.client.get(reverse("products:product_detail", args=[self.product.pk]))
        self.assertContains(response, 'class="workflow-chips"')


class ApprovalWorklistTests(NavigationFixture):
    def test_lists_drafts_for_approvers_only(self):
        from apps.core.navigation import approval_items

        Assessment.objects.create(configuration=self.configuration)
        groups = approval_items(self.approver)
        kinds = [item["kind"] for item in groups[0]["items"]]
        self.assertIn("Product", kinds)
        self.assertIn("Hardware revision", kinds)
        self.assertIn("Configuration", kinds)
        self.assertIn("Assessment", kinds)
        self.assertEqual(approval_items(self.editor), [])

    def test_risk_register_appears_once_it_has_entries(self):
        from apps.core.navigation import approval_items

        def kinds():
            return [i["kind"] for g in approval_items(self.approver) for i in g["items"]]

        self.assertNotIn("Risk register", kinds())
        self._asset()
        self.assertIn("Risk register", kinds())

    def test_page_nav_link_and_dashboard_widget(self):
        self.client.force_login(self.approver)
        response = self.client.get(reverse("core:approvals"))
        self.assertContains(response, "Waiting for your approval")
        self.assertContains(response, "TempSense EU 1.0")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, f'href="{reverse("core:approvals")}"')
        self.assertContains(response, "Waiting for your approval")
        self.client.force_login(self.editor)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, f'href="{reverse("core:approvals")}"')


class RiskApprovalViewTests(NavigationFixture):
    def _approve(self, user):
        self.client.force_login(user)
        return self.client.post(reverse("risk:approve", args=[self.configuration.pk]))

    def test_approver_approves_register_with_snapshot(self):
        from apps.risk.models import RiskAssessmentStatus

        self._asset()
        self.client.force_login(self.approver)
        register = self.client.get(reverse("risk:register", args=[self.configuration.pk]))
        approve_url = reverse("risk:approve", args=[self.configuration.pk])
        self.assertContains(register, f'<form method="post" action="{approve_url}">')
        self.assertNotContains(register, "<title>Risk register · TempSense EU 1.0 · Aavistin\n")
        self._approve(self.approver)
        risk_assessment = self.configuration.risk_assessments.get()
        self.assertEqual(risk_assessment.status, RiskAssessmentStatus.APPROVED)
        self.assertIsNotNone(risk_assessment.snapshot)
        self.assertEqual(risk_assessment.approved_by, self.approver)
        response = self.client.get(reverse("risk:register", args=[self.configuration.pk]))
        self.assertContains(response, "Approved</span> on")

    def test_editor_cannot_approve_and_empty_register_is_refused(self):
        self._asset()
        self._approve(self.editor)
        self.assertFalse(self.configuration.risk_assessments.exists())
        self.configuration.hardware_revision.hardware_variant.product.risk_entries.all().delete()
        self._approve(self.approver)
        self.assertFalse(self.configuration.risk_assessments.exists())

    def test_stale_register_is_approved_again_as_a_new_snapshot(self):
        self._asset()
        self._approve(self.approver)
        self.configuration.risk_assessments.update(stale=True)
        self._approve(self.approver)
        self.assertEqual(self.configuration.risk_assessments.count(), 2)


class AssessmentApprovalCheckTests(NavigationFixture):
    def test_open_questions_need_explicit_confirmation(self):
        assessment = Assessment.objects.create(configuration=self.configuration)
        self.client.force_login(self.approver)
        url = reverse("assessments:assessment_approve", args=[assessment.pk])
        detail = self.client.get(reverse("assessments:assessment_detail", args=[assessment.pk]))
        self.assertContains(detail, "Before you approve")
        self.assertContains(detail, 'name="confirm_open"')

        self.client.post(url)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, AssessmentStatus.DRAFT)

        self.client.post(url, {"confirm_open": "1"})
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, AssessmentStatus.APPROVED)

    def test_complete_questionnaire_needs_no_confirmation(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        self.client.force_login(self.approver)
        self.client.post(reverse("assessments:assessment_approve", args=[assessment.pk]))
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, AssessmentStatus.APPROVED)


class QuestionOwnershipTests(NavigationFixture):
    def _post(self, **overrides):
        payload = {
            "question_id": "has_power_source",
            "owner_type": "hardware_revision",
            "owner_id": str(self.revision.pk),
            "question_type": "boolean",
            "value": "true",
        }
        payload.update(overrides)
        self.client.force_login(self.editor)
        return self.client.post(
            reverse("assessments:answer_question", args=[self.configuration.pk]), payload
        )

    def test_rows_show_the_level_and_owner(self):
        self.client.force_login(self.editor)
        response = self.client.get(
            reverse("assessments:configuration_detail", args=[self.configuration.pk])
        )
        self.assertContains(response, "Hardware · EU variant rev A")
        self.assertContains(response, "Product · TempSense")
        self.assertContains(response, "Hardware (")

    def test_save_confirms_where_the_answer_went_and_keeps_filters(self):
        response = self._post(return_query="show=open&level=hardware&evil=1")
        self.assertIn("?show=open&level=hardware#q-", response["Location"])
        self.assertNotIn("evil", response["Location"])
        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("Answer saved on Hardware" in m for m in messages))

    def test_owner_outside_the_configuration_is_rejected(self):
        other_variant = HardwareVariant.objects.create(product=self.product, name="US", slug="us")
        other = HardwareRevision.objects.create(hardware_variant=other_variant, label="B")
        self._post(owner_id=str(other.pk))
        self.assertFalse(Answer.objects.filter(hardware_revision=other).exists())


class SlugDerivationTests(NavigationFixture):
    def test_add_forms_derive_unique_slugs_from_names(self):
        self.client.force_login(self.editor)
        url = reverse("products:hardware_variant_create", args=[self.product.pk])
        self.client.post(url, {"name": "EU Variant"})
        self.client.post(url, {"name": "EU Variant!"})
        slugs = set(self.product.hw_variants.values_list("slug", flat=True))
        self.assertIn("eu-variant-2", slugs)
        self.assertIn("eu-variant-3", slugs)

    def test_typed_slug_is_kept(self):
        self.client.force_login(self.editor)
        url = reverse("products:hardware_variant_create", args=[self.product.pk])
        self.client.post(url, {"name": "Asia", "slug": "apac"})
        self.assertTrue(self.product.hw_variants.filter(slug="apac").exists())


class PortfolioProgressTests(NavigationFixture):
    def test_portfolio_shows_progress_and_family_anchors(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("orgs:portfolio"))
        self.assertContains(response, f'id="family-{self.family.pk}"')
        self.assertContains(response, "Questions answered")
