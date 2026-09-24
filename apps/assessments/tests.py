import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.evidence.models import Evidence, EvidenceKind
from apps.evidence.services import link_evidence
from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment, SoDPolicy
from apps.packages.importer import approve_package, import_package
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareRelease,
    TargetMarket,
)

from .carryforward import confirm_answers, copy_answers_forward
from .evaluation import evaluate_configuration
from .models import Answer, Assessment, AssessmentStatus
from .resolution import resolve_answer, resolve_answers
from .services import (
    AssessmentError,
    SoDViolation,
    approve_assessment,
    recompute_all_staleness,
    recompute_staleness,
)
from .tasks import refresh_staleness_task

DEMO_DIR = Path(settings.BASE_DIR) / "packages" / "demo-widget-safety"
PACKAGES_DIR = Path(settings.BASE_DIR) / "packages"


def load_demo(version: str) -> dict:
    with (DEMO_DIR / f"{version}.json").open() as f:
        return json.load(f)


def load_package(dirname: str, version: str) -> dict:
    with (PACKAGES_DIR / dirname / f"{version}.json").open() as f:
        return json.load(f)


class ConfigurationFixture(TestCase):
    """Builds one EU-market configuration with the demo package approved."""

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
        self.release = SoftwareRelease.objects.create(product=self.product, version="1.0")
        self.configuration = Configuration.objects.create(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )

        self.package = import_package(load_demo("1.0.0"), is_official=True)
        approve_package(self.package)

        self.editor = User.objects.create_user(username="edna", password="x")
        self.approver = User.objects.create_user(username="ana", password="x")
        RoleAssignment.objects.create(
            role=Role.EDITOR, user=self.editor, product_family=self.family
        )
        RoleAssignment.objects.create(
            role=Role.APPROVER, user=self.approver, product_family=self.family
        )
        RoleAssignment.objects.create(
            role=Role.VIEWER, user=self.editor, product_family=self.family
        )


class AnswerModelTests(ConfigurationFixture):
    def test_exactly_one_owner_required(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.create(question_id="has_power_source", value=True)

    def test_two_owners_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Answer.objects.create(
                question_id="has_power_source",
                value=True,
                product=self.product,
                hardware_revision=self.revision,
            )

    def test_overriding_inherited_answer_requires_justification(self):
        Answer.objects.create(question_id="rated_power_watts", value=20, product=self.product)
        override = Answer(
            question_id="rated_power_watts", value=150, hardware_revision=self.revision
        )
        with self.assertRaises(ValidationError):
            override.full_clean()

        override.override_justification = "Rev A uses a higher-power supply."
        override.full_clean()
        override.save()
        self.assertEqual(override.value, 150)

    def test_same_value_override_does_not_require_justification(self):
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)
        same_value = Answer(
            question_id="is_toy_widget", value=False, hardware_revision=self.revision
        )
        same_value.full_clean()  # no justification needed; value matches ancestor


class ResolutionTests(ConfigurationFixture):
    def test_hardware_level_answer_overrides_product_level(self):
        Answer.objects.create(question_id="rated_power_watts", value=20, product=self.product)
        Answer.objects.create(
            question_id="rated_power_watts",
            value=150,
            hardware_revision=self.revision,
            override_justification="override",
        )
        answer = resolve_answer(self.configuration, "rated_power_watts")
        self.assertEqual(answer.value, 150)

    def test_unanswered_question_resolves_to_none(self):
        answer = resolve_answer(self.configuration, "has_power_source")
        self.assertIsNone(answer)

    def test_only_matching_jurisdiction_packages_are_active(self):
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=20, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)
        resolved, packages = resolve_answers(self.configuration)
        self.assertEqual([p.source for p in packages], ["demo-widget-safety"])
        self.assertIn("has_power_source", resolved)

    def test_no_target_market_means_no_active_packages(self):
        self.variant.target_markets.clear()
        resolved, packages = resolve_answers(self.configuration)
        self.assertEqual(list(packages), [])
        self.assertEqual(resolved, {})

    def test_conditional_question_is_filtered_by_condition(self):
        content = dict(load_demo("1.0.0"))
        content["source"] = "demo-conditional"
        content["version"] = "1.0.0"
        content["questions"] = content["questions"] + [
            {
                "id": "antenna_gain_dbi",
                "type": "number",
                "level": "hardware",
                "condition": {"var": "has_power_source"},
            }
        ]
        package = import_package(content, is_official=True)
        approve_package(package)

        # has_power_source unanswered (falsy) -> antenna_gain_dbi's condition
        # never becomes true, so it's excluded from the resolved set.
        resolved, _ = resolve_answers(self.configuration)
        self.assertNotIn("antenna_gain_dbi", resolved)

        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        resolved, _ = resolve_answers(self.configuration)
        self.assertIn("antenna_gain_dbi", resolved)


class EvaluationTests(ConfigurationFixture):
    def _answer(self, has_power, watts, is_toy):
        Answer.objects.create(
            question_id="has_power_source", value=has_power, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=watts, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=is_toy, product=self.product)

    def test_high_power_triggers_caution_finding(self):
        self._answer(has_power=True, watts=150, is_toy=False)
        evaluation = evaluate_configuration(self.configuration)
        result = evaluation["results"][0]
        self.assertTrue(result["in_scope"])
        self.assertIn("high_power", result["classifications"])
        finding_ids = [f["id"] for f in evaluation["findings"]]
        self.assertIn("high_power_caution", finding_ids)

    def test_toy_widget_excluded_from_scope(self):
        self._answer(has_power=True, watts=5, is_toy=True)
        evaluation = evaluate_configuration(self.configuration)
        self.assertFalse(evaluation["results"][0]["in_scope"])

    def test_requirements_only_listed_when_in_scope(self):
        self._answer(has_power=False, watts=0, is_toy=False)
        evaluation = evaluate_configuration(self.configuration)
        self.assertEqual(evaluation["results"][0]["requirements"], [])


class CarryForwardTests(ConfigurationFixture):
    def test_answers_copied_forward_need_confirmation(self):
        Answer.objects.create(
            question_id="is_toy_widget", value=False, software_release=self.release
        )
        next_release = SoftwareRelease.objects.create(product=self.product, version="2.0")

        created = copy_answers_forward(self.release, next_release, actor=self.editor)
        self.assertEqual(len(created), 1)
        copied = Answer.objects.get(software_release=next_release, question_id="is_toy_widget")
        self.assertTrue(copied.needs_confirmation)
        self.assertEqual(copied.value, False)


class EuCraConfigurationFixture(TestCase):
    """Mirrors ConfigurationFixture but approves the real eu-cra package,
    to exercise its classification -> assessment_routes/finding_rules
    wiring (the class__ synthetic vars) through evaluate_configuration.
    """

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
        self.release = SoftwareRelease.objects.create(product=self.product, version="1.0")
        self.configuration = Configuration.objects.create(
            name="TempSense EU 1.0",
            hardware_revision=self.revision,
            software_release=self.release,
        )

        self.package = import_package(load_package("eu-cra", "1.0.0"), is_official=True)
        approve_package(self.package)

    def _answer(self, **values):
        for question_id, value in values.items():
            Answer.objects.create(
                question_id=question_id, value=value, hardware_revision=self.revision
            )


class EuCraEvaluationTests(EuCraConfigurationFixture):
    def test_default_classification_gets_internal_control_route(self):
        self._answer(
            is_free_and_open_source=False,
            is_commercial_activity=True,
            is_annex_iii_important_product=False,
            is_annex_iii_critical_product=False,
        )
        evaluation = evaluate_configuration(self.configuration)
        result = evaluation["results"][0]
        self.assertTrue(result["in_scope"])
        self.assertEqual(result["classifications"], ["default"])
        self.assertEqual(result["assessment_routes"], ["internal_control"])
        self.assertEqual(evaluation["findings"], [])

    def test_important_classification_gets_third_party_route_and_finding(self):
        self._answer(
            is_free_and_open_source=False,
            is_commercial_activity=True,
            is_annex_iii_important_product=True,
            is_annex_iii_critical_product=False,
        )
        evaluation = evaluate_configuration(self.configuration)
        result = evaluation["results"][0]
        self.assertTrue(result["in_scope"])
        self.assertEqual(result["classifications"], ["important"])
        self.assertEqual(result["assessment_routes"], ["third_party_assessment"])
        finding_ids = [f["id"] for f in evaluation["findings"]]
        self.assertIn("important_or_critical_needs_third_party", finding_ids)

    def test_foss_non_commercial_is_out_of_scope(self):
        self._answer(is_free_and_open_source=True, is_commercial_activity=False)
        evaluation = evaluate_configuration(self.configuration)
        result = evaluation["results"][0]
        self.assertFalse(result["in_scope"])
        finding_ids = [f["id"] for f in evaluation["findings"]]
        self.assertIn("monetisation_changes_scope", finding_ids)

    def test_confirm_answers_clears_flag(self):
        Answer.objects.create(
            question_id="is_toy_widget",
            value=False,
            software_release=self.release,
            needs_confirmation=True,
        )
        confirmed = confirm_answers(Answer.objects.filter(software_release=self.release))
        self.assertEqual(confirmed, 1)
        self.assertFalse(Answer.objects.get().needs_confirmation)


class ApprovalTests(ConfigurationFixture):
    def _ready_answers(self):
        Answer.objects.create(
            question_id="has_power_source",
            value=True,
            hardware_revision=self.revision,
            created_by=self.editor,
        )
        Answer.objects.create(
            question_id="rated_power_watts",
            value=20,
            hardware_revision=self.revision,
            created_by=self.editor,
        )
        Answer.objects.create(
            question_id="is_toy_widget",
            value=False,
            product=self.product,
            created_by=self.editor,
        )

    def test_approve_freezes_snapshot(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)
        self.assertEqual(assessment.status, AssessmentStatus.APPROVED)
        self.assertIsNotNone(assessment.snapshot)
        self.assertFalse(assessment.stale)
        self.assertFalse(assessment.sod_warning)

    def test_cannot_approve_twice(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)
        with self.assertRaises(AssessmentError):
            approve_assessment(assessment, actor=self.approver)

    def test_sod_enforce_blocks_self_approval(self):
        self.org.sod_policy = SoDPolicy.ENFORCE
        self.org.save()
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        with self.assertRaises(SoDViolation):
            approve_assessment(assessment, actor=self.editor)

    def test_sod_warn_allows_but_flags(self):
        self.org.sod_policy = SoDPolicy.WARN
        self.org.save()
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.editor)
        self.assertTrue(assessment.sod_warning)
        self.assertEqual(assessment.status, AssessmentStatus.APPROVED)

    def test_sod_off_allows_without_flag(self):
        self.org.sod_policy = SoDPolicy.OFF
        self.org.save()
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.editor)
        self.assertFalse(assessment.sod_warning)

    def test_different_approver_never_triggers_sod(self):
        self.org.sod_policy = SoDPolicy.ENFORCE
        self.org.save()
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)  # did not edit anything
        self.assertFalse(assessment.sod_warning)


class StalenessTests(ConfigurationFixture):
    def _ready_answers(self):
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=20, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)

    def test_not_stale_immediately_after_approval(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)
        self.assertFalse(recompute_staleness(assessment))

    def test_answer_change_makes_it_stale(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)

        answer = Answer.objects.get(question_id="rated_power_watts")
        answer.value = 150
        answer.override_justification = "changed after approval"
        answer.save()

        self.assertTrue(recompute_staleness(assessment))
        assessment.refresh_from_db()
        self.assertTrue(assessment.stale)

    def test_new_approved_package_version_makes_it_stale(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)

        v2 = import_package(load_demo("1.1.0"), is_official=True)
        approve_package(v2)

        self.assertTrue(recompute_staleness(assessment))

    def test_draft_assessment_is_never_stale(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        self.assertFalse(recompute_staleness(assessment))


class EvidenceStalenessTests(ConfigurationFixture):
    """apps.evidence linked to a requirement feeds evaluate_configuration's
    results, so it's picked up by the same recompute_staleness diff (see
    docs/architecture.md, "Evidence")."""

    def _ready_answers(self):
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=20, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)

    def _make_evidence(self, **kwargs):
        return Evidence.objects.create(
            product=self.product,
            title=kwargs.pop("title", "Safety manual"),
            kind=EvidenceKind.TEXT,
            reference_text=kwargs.pop("reference_text", "See QMS wiki"),
            **kwargs,
        )

    def _link_to_manual_requirement(self, evidence):
        return link_evidence(
            evidence, requirement=("demo-widget-safety", "1.0.0", "provide_widget_manual")
        )

    def test_new_requirement_evidence_link_makes_it_stale(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)

        self._link_to_manual_requirement(self._make_evidence())
        self.assertTrue(recompute_staleness(assessment))

    def test_unchanged_evidence_stays_fresh(self):
        self._ready_answers()
        self._link_to_manual_requirement(self._make_evidence())
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)
        self.assertFalse(recompute_staleness(assessment))

    def test_expired_evidence_makes_it_stale(self):
        from datetime import date, timedelta

        self._ready_answers()
        evidence = self._make_evidence(valid_until=date.today() + timedelta(days=1))
        self._link_to_manual_requirement(evidence)
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)

        evidence.valid_until = date.today() - timedelta(days=1)
        evidence.save()
        self.assertTrue(recompute_staleness(assessment))

    def test_superseded_evidence_makes_it_stale(self):
        self._ready_answers()
        evidence = self._make_evidence()
        self._link_to_manual_requirement(evidence)
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)

        Evidence.objects.create(
            product=self.product,
            title="Safety manual v2",
            kind=EvidenceKind.TEXT,
            reference_text="see wiki v2",
            supersedes=evidence,
        )
        self.assertTrue(recompute_staleness(assessment))


class BackgroundTaskTests(ConfigurationFixture):
    """The immediate task backend runs synchronously in tests (conftest.py),
    so these call .enqueue() directly rather than needing a worker."""

    def _ready_answers(self):
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=20, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)

    def test_recompute_all_staleness_checks_only_approved(self):
        self._ready_answers()
        Assessment.objects.create(configuration=self.configuration)  # draft, not counted
        approved = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(approved, actor=self.approver)

        checked, newly_stale = recompute_all_staleness()
        self.assertEqual(checked, 1)
        self.assertEqual(newly_stale, 0)

    def test_task_flips_stale_flag(self):
        self._ready_answers()
        assessment = Assessment.objects.create(configuration=self.configuration)
        approve_assessment(assessment, actor=self.approver)

        answer = Answer.objects.get(question_id="rated_power_watts")
        answer.value = 150
        answer.override_justification = "changed after approval"
        answer.save()

        result = refresh_staleness_task.enqueue()
        self.assertEqual(result.status, "SUCCESSFUL")
        assessment.refresh_from_db()
        self.assertTrue(assessment.stale)


class ViewTests(ConfigurationFixture):
    def _answer_payload(self, **overrides):
        payload = {
            "question_id": "has_power_source",
            "owner_type": "hardware_revision",
            "owner_id": str(self.revision.pk),
            "value": "true",
            "justification": "",
        }
        payload.update(overrides)
        return payload

    def test_configuration_detail_requires_login(self):
        response = self.client.get(
            reverse("assessments:configuration_detail", args=[self.configuration.pk])
        )
        self.assertEqual(response.status_code, 302)

    def test_editor_can_answer_question(self):
        self.client.force_login(self.editor)
        response = self.client.post(
            reverse("assessments:answer_question", args=[self.configuration.pk]),
            self._answer_payload(),
        )
        self.assertEqual(response.status_code, 302)
        answer = Answer.objects.get(question_id="has_power_source")
        self.assertEqual(answer.value, True)
        self.assertEqual(answer.hardware_revision, self.revision)

    def test_viewer_cannot_answer_question(self):
        viewer = User.objects.create_user(username="vera", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=viewer, product_family=self.family)
        self.client.force_login(viewer)
        self.client.post(
            reverse("assessments:answer_question", args=[self.configuration.pk]),
            self._answer_payload(),
        )
        self.assertFalse(Answer.objects.filter(question_id="has_power_source").exists())

    def test_approver_can_approve_via_view(self):
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=20, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)
        assessment = Assessment.objects.create(configuration=self.configuration)

        self.client.force_login(self.approver)
        response = self.client.post(
            reverse("assessments:assessment_approve", args=[assessment.pk])
        )
        self.assertEqual(response.status_code, 302)
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, AssessmentStatus.APPROVED)

    def test_non_approver_cannot_approve_via_view(self):
        assessment = Assessment.objects.create(configuration=self.configuration)
        self.client.force_login(self.editor)
        self.client.post(reverse("assessments:assessment_approve", args=[assessment.pk]))
        assessment.refresh_from_db()
        self.assertEqual(assessment.status, AssessmentStatus.DRAFT)
