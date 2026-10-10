import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.assessments.models import Answer
from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment
from apps.packages.importer import approve_package, import_package
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareRelease,
    TargetMarket,
)

from .approval import (
    RiskAssessmentError,
    approve_risk_assessment,
    recompute_all_staleness,
    recompute_staleness,
)
from .consistency import check_threat_hazard_consistency
from .models import (
    AssetRating,
    CauseType,
    Control,
    EntryType,
    HazardCause,
    ImpactCategory,
    Rating,
    RiskAssessment,
    RiskAssessmentStatus,
    RiskEntry,
    SuggestionStatus,
    ThreatConsequence,
    Treatment,
    TreatmentType,
)
from .rating import evaluate_entry_rating, evaluate_residual_rating, threat_severity
from .resolution import register_for_configuration
from .suggestions import accept_suggestion, dismiss_suggestion, pending_suggestions
from .tasks import refresh_staleness_task

PACKAGES_DIR = Path(settings.BASE_DIR) / "packages"


def load_package(dirname: str, version: str) -> dict:
    with (PACKAGES_DIR / dirname / f"{version}.json").open() as f:
        return json.load(f)


class RiskFixture(TestCase):
    """One EU-market configuration with demo-widget-safety, both demo
    methods and the demo catalog all approved."""

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

        self.requirement_package = import_package(
            load_package("demo-widget-safety", "1.1.0"), is_official=True
        )
        approve_package(self.requirement_package)

        self.cia_method = import_package(
            load_package("default-cia-5x5", "1.0.0"), kind=PackageKind.METHOD, is_official=True
        )
        approve_package(self.cia_method)
        self.safety_method = import_package(
            load_package("demo-safety-5x5", "1.0.0"), kind=PackageKind.METHOD, is_official=True
        )
        approve_package(self.safety_method)
        self.catalog = import_package(
            load_package("demo-widget-risks", "1.0.0"), kind=PackageKind.CATALOG, is_official=True
        )
        approve_package(self.catalog)

        self.editor = User.objects.create_user(username="edna", password="x")
        self.approver = User.objects.create_user(username="ana", password="x")
        RoleAssignment.objects.create(
            role=Role.EDITOR, user=self.editor, product_family=self.family
        )
        RoleAssignment.objects.create(
            role=Role.APPROVER, user=self.approver, product_family=self.family
        )

    def make_asset(self, label="Widget firmware"):
        return RiskEntry.objects.create(
            product=self.product, entry_type=EntryType.ASSET, label=label
        )

    def make_threat(
        self, asset, label="Wireless eavesdropping", violates="confidentiality", **kwargs
    ):
        entry = RiskEntry(
            product=self.product,
            entry_type=EntryType.THREAT,
            label=label,
            asset=asset,
            violates=violates,
            **kwargs,
        )
        entry.full_clean()
        entry.save()
        return entry

    def make_hazard(self, label="Overheating fire", **kwargs):
        entry = RiskEntry(product=self.product, entry_type=EntryType.HAZARD, label=label, **kwargs)
        entry.full_clean()
        entry.save()
        return entry


class RiskEntryModelTests(RiskFixture):
    def test_at_most_one_scope(self):
        entry = RiskEntry(
            product=self.product,
            entry_type=EntryType.ASSET,
            label="x",
            scope_hardware_variant=self.variant,
            scope_software_release=self.release,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_threat_requires_violates(self):
        entry = RiskEntry(product=self.product, entry_type=EntryType.THREAT, label="x")
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_only_threats_target_an_asset(self):
        asset = self.make_asset()
        entry = RiskEntry(
            product=self.product, entry_type=EntryType.HAZARD, label="x", asset=asset
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_delta_must_be_scoped(self):
        base = self.make_hazard()
        delta = RiskEntry(
            product=self.product, entry_type=EntryType.HAZARD, label="x", base_entry=base
        )
        with self.assertRaises(ValidationError):
            delta.full_clean()

    def test_dismissed_requires_reason(self):
        entry = RiskEntry(
            product=self.product,
            entry_type=EntryType.HAZARD,
            label="x",
            suggestion_status=SuggestionStatus.DISMISSED,
        )
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_is_baseline(self):
        baseline = self.make_hazard()
        self.assertTrue(baseline.is_baseline)
        scoped = RiskEntry(
            product=self.product,
            entry_type=EntryType.HAZARD,
            label="y",
            scope_software_release=self.release,
        )
        scoped.full_clean()
        self.assertFalse(scoped.is_baseline)


class RatingSubModelTests(RiskFixture):
    def test_hazard_rating_requires_severity(self):
        hazard = self.make_hazard()
        rating = Rating(entry=hazard, method=self.safety_method, likelihood=3)
        with self.assertRaises(ValidationError):
            rating.full_clean()

    def test_threat_rating_forbids_severity(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        rating = Rating(entry=threat, method=self.cia_method, severity=3, likelihood=3)
        with self.assertRaises(ValidationError):
            rating.full_clean()

    def test_one_rating_per_entry_per_method(self):
        hazard = self.make_hazard()
        Rating.objects.create(entry=hazard, method=self.safety_method, severity=3, likelihood=3)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Rating.objects.create(
                entry=hazard, method=self.safety_method, severity=4, likelihood=4
            )

    def test_consequence_override_requires_justification(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        consequence = ThreatConsequence(
            threat=threat,
            impact_category=ImpactCategory.OPERATIONAL,
            severity=4,
            severity_is_override=True,
        )
        with self.assertRaises(ValidationError):
            consequence.full_clean()

    def test_hazard_cause_cyberattack_requires_threat(self):
        hazard = self.make_hazard()
        cause = HazardCause(hazard=hazard, cause_type=CauseType.CYBERATTACK)
        with self.assertRaises(ValidationError):
            cause.full_clean()

    def test_hazard_cause_non_cyberattack_forbids_threat(self):
        hazard = self.make_hazard()
        asset = self.make_asset()
        threat = self.make_threat(asset)
        cause = HazardCause(hazard=hazard, cause_type=CauseType.HARDWARE_FAILURE, threat=threat)
        with self.assertRaises(ValidationError):
            cause.full_clean()


class AssetRatingTests(RiskFixture):
    def test_one_rating_per_asset_per_method_per_property(self):
        asset = self.make_asset()
        AssetRating.objects.create(
            entry=asset, method=self.cia_method, property="confidentiality", severity=3
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            AssetRating.objects.create(
                entry=asset, method=self.cia_method, property="confidentiality", severity=4
            )

    def test_different_properties_are_independent(self):
        asset = self.make_asset()
        AssetRating.objects.create(
            entry=asset, method=self.cia_method, property="confidentiality", severity=3
        )
        AssetRating.objects.create(
            entry=asset, method=self.cia_method, property="integrity", severity=5
        )
        self.assertEqual(asset.asset_ratings.count(), 2)


class ResolutionTests(RiskFixture):
    def test_baseline_only_when_no_deltas(self):
        baseline = self.make_hazard()
        view = register_for_configuration(self.configuration)
        self.assertEqual([e.id for e in view], [baseline.id])

    def test_matching_delta_replaces_baseline(self):
        baseline = self.make_hazard(label="Base")
        delta = RiskEntry(
            product=self.product,
            entry_type=EntryType.HAZARD,
            label="Delta",
            scope_software_release=self.release,
            base_entry=baseline,
            delta_justification="secure boot lowers likelihood",
        )
        delta.full_clean()
        delta.save()

        view = register_for_configuration(self.configuration)
        labels = {e.label for e in view}
        self.assertEqual(labels, {"Delta"})

    def test_delta_scoped_to_other_release_is_not_included(self):
        other_release = SoftwareRelease.objects.create(product=self.product, version="2.0")
        baseline = self.make_hazard(label="Base")
        delta = RiskEntry(
            product=self.product,
            entry_type=EntryType.HAZARD,
            label="Delta",
            scope_software_release=other_release,
            base_entry=baseline,
        )
        delta.full_clean()
        delta.save()

        view = register_for_configuration(self.configuration)
        labels = {e.label for e in view}
        self.assertEqual(labels, {"Base"})

    def test_dismissed_entries_excluded(self):
        RiskEntry.objects.create(
            product=self.product,
            entry_type=EntryType.HAZARD,
            label="Dismissed",
            suggestion_status=SuggestionStatus.DISMISSED,
            dismissal_reason="not applicable",
        )
        view = register_for_configuration(self.configuration)
        self.assertEqual(view, [])


class RatingComputationTests(RiskFixture):
    def test_threat_severity_is_worst_consequence(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        ThreatConsequence.objects.create(
            threat=threat, impact_category=ImpactCategory.OPERATIONAL, severity=2
        )
        ThreatConsequence.objects.create(
            threat=threat, impact_category=ImpactCategory.FINANCIAL, severity=4
        )
        self.assertEqual(threat_severity(threat), 4)

    def test_threat_severity_none_without_consequences(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        self.assertIsNone(threat_severity(threat))

    def test_evaluate_entry_rating_for_hazard(self):
        hazard = self.make_hazard()
        Rating.objects.create(entry=hazard, method=self.safety_method, severity=5, likelihood=4)
        result = evaluate_entry_rating(hazard, self.safety_method)
        self.assertEqual(result["level"], "high")
        self.assertEqual(result["acceptance"], "must_treat")

    def test_evaluate_entry_rating_for_threat_uses_derived_severity(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        ThreatConsequence.objects.create(
            threat=threat, impact_category=ImpactCategory.OPERATIONAL, severity=2
        )
        Rating.objects.create(entry=threat, method=self.cia_method, likelihood=2)
        result = evaluate_entry_rating(threat, self.cia_method)
        self.assertEqual(result["severity"], 2)
        self.assertEqual(result["level"], "low")

    def test_unrated_entry_returns_nones(self):
        hazard = self.make_hazard()
        result = evaluate_entry_rating(hazard, self.safety_method)
        self.assertEqual(
            result, {"severity": None, "likelihood": None, "level": None, "acceptance": None}
        )

    def test_residual_rating(self):
        hazard = self.make_hazard()
        Rating.objects.create(entry=hazard, method=self.safety_method, severity=5, likelihood=4)
        treatment = Treatment.objects.create(
            entry=hazard,
            method=self.safety_method,
            treatment_type=TreatmentType.MITIGATE,
            residual_severity=2,
            residual_likelihood=2,
            justification="added thermal fuse",
        )
        result = evaluate_residual_rating(treatment)
        self.assertEqual(result["level"], "low")


class ConsistencyTests(RiskFixture):
    def _linked_threat_and_hazard(
        self, hazard_severity, hazard_likelihood, consequence_severity=3
    ):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        hazard = self.make_hazard()
        Rating.objects.create(
            entry=hazard,
            method=self.safety_method,
            severity=hazard_severity,
            likelihood=hazard_likelihood,
        )
        ThreatConsequence.objects.create(
            threat=threat,
            impact_category=ImpactCategory.SAFETY,
            severity=consequence_severity,
            hazard=hazard,
        )
        return threat, hazard

    def test_no_issue_without_linked_hazard(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        self.assertEqual(check_threat_hazard_consistency(threat), [])

    def test_accepting_threat_with_unacceptable_hazard_is_flagged(self):
        threat, hazard = self._linked_threat_and_hazard(hazard_severity=5, hazard_likelihood=4)
        Treatment.objects.create(
            entry=threat, method=self.cia_method, treatment_type=TreatmentType.ACCEPT
        )
        issues = check_threat_hazard_consistency(threat)
        self.assertTrue(any(i["code"] == "unacceptable_linked_hazard" for i in issues))

    def test_accepting_threat_with_acceptable_hazard_is_not_flagged(self):
        threat, hazard = self._linked_threat_and_hazard(hazard_severity=1, hazard_likelihood=1)
        Treatment.objects.create(
            entry=threat, method=self.cia_method, treatment_type=TreatmentType.ACCEPT
        )
        issues = check_threat_hazard_consistency(threat)
        self.assertEqual([i for i in issues if i["code"] == "unacceptable_linked_hazard"], [])

    def test_severity_mapping_violation(self):
        # default-cia-5x5 maps its severities 1:1 onto demo-safety-5x5.
        # A consequence severity of 5 implies the hazard must be rated >= 5.
        threat, hazard = self._linked_threat_and_hazard(
            hazard_severity=2, hazard_likelihood=1, consequence_severity=5
        )
        Rating.objects.create(entry=threat, method=self.cia_method, likelihood=2)
        issues = check_threat_hazard_consistency(threat)
        self.assertTrue(any(i["code"] == "severity_mapping_violation" for i in issues))

    def test_severity_mapping_satisfied_is_not_flagged(self):
        threat, hazard = self._linked_threat_and_hazard(
            hazard_severity=5, hazard_likelihood=1, consequence_severity=5
        )
        Rating.objects.create(entry=threat, method=self.cia_method, likelihood=2)
        issues = check_threat_hazard_consistency(threat)
        self.assertEqual([i for i in issues if i["code"] == "severity_mapping_violation"], [])


class SuggestionTests(RiskFixture):
    def _answer_configuration_for_triggers(self):
        from apps.assessments.models import Answer

        Answer.objects.create(
            question_id="has_wireless", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=100, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)

    def test_pending_suggestions_lists_triggered_entries(self):
        self._answer_configuration_for_triggers()
        suggestions = pending_suggestions(self.configuration)
        ids = {s["entry_id"] for s in suggestions}
        self.assertEqual(
            ids, {"wireless_eavesdropping", "unauthorized_wireless_access", "overheating_fire"}
        )

    def test_no_suggestions_without_matching_context(self):
        suggestions = pending_suggestions(self.configuration)
        self.assertEqual(suggestions, [])

    def test_accept_suggestion_creates_entry(self):
        self._answer_configuration_for_triggers()
        entry = accept_suggestion(
            self.product, self.catalog, "wireless_eavesdropping", actor=self.editor
        )
        self.assertEqual(entry.suggestion_status, SuggestionStatus.ACCEPTED)
        self.assertEqual(entry.entry_type, EntryType.THREAT)
        self.assertEqual(entry.violates, "confidentiality")
        self.assertEqual(entry.source_catalog_entry_id, "wireless_eavesdropping")

    def test_accept_suggestion_creates_non_cyberattack_hazard_causes(self):
        self._answer_configuration_for_triggers()
        entry = accept_suggestion(
            self.product, self.catalog, "overheating_fire", actor=self.editor
        )
        causes = {c.cause_type for c in entry.causes.all()}
        self.assertIn(CauseType.HARDWARE_FAILURE, causes)
        # cyberattack is declared on the catalog entry but needs a manual threat link.
        self.assertNotIn(CauseType.CYBERATTACK, causes)

    def test_accepted_entry_no_longer_suggested(self):
        self._answer_configuration_for_triggers()
        accept_suggestion(self.product, self.catalog, "wireless_eavesdropping", actor=self.editor)
        suggestions = pending_suggestions(self.configuration)
        ids = {s["entry_id"] for s in suggestions}
        self.assertNotIn("wireless_eavesdropping", ids)

    def test_dismiss_suggestion_requires_reason(self):
        self._answer_configuration_for_triggers()
        with self.assertRaises(ValueError):
            dismiss_suggestion(
                self.product, self.catalog, "wireless_eavesdropping", reason="", actor=self.editor
            )

    def test_dismiss_suggestion_stops_it_being_suggested_again(self):
        self._answer_configuration_for_triggers()
        entry = dismiss_suggestion(
            self.product,
            self.catalog,
            "wireless_eavesdropping",
            reason="Not a concern for this deployment",
            actor=self.editor,
        )
        self.assertEqual(entry.suggestion_status, SuggestionStatus.DISMISSED)
        suggestions = pending_suggestions(self.configuration)
        ids = {s["entry_id"] for s in suggestions}
        self.assertNotIn("wireless_eavesdropping", ids)


class ApprovalTests(RiskFixture):
    def _basic_hazard_scenario(self):
        hazard = self.make_hazard()
        Rating.objects.create(entry=hazard, method=self.safety_method, severity=2, likelihood=2)
        return hazard

    def test_approve_freezes_snapshot(self):
        self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(risk_assessment, actor=self.approver)
        self.assertEqual(risk_assessment.status, RiskAssessmentStatus.APPROVED)
        self.assertIsNotNone(risk_assessment.snapshot)
        self.assertFalse(risk_assessment.stale)
        self.assertIn(["demo-safety-5x5", "1.0.0"], risk_assessment.snapshot["methods"])

    def test_cannot_approve_twice(self):
        self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(risk_assessment, actor=self.approver)
        with self.assertRaises(RiskAssessmentError):
            approve_risk_assessment(risk_assessment, actor=self.approver)

    def test_not_stale_immediately_after_approval(self):
        self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(risk_assessment, actor=self.approver)
        self.assertFalse(recompute_staleness(risk_assessment))

    def test_rating_change_makes_it_stale(self):
        hazard = self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(risk_assessment, actor=self.approver)

        rating = Rating.objects.get(entry=hazard, method=self.safety_method)
        rating.likelihood = 5
        rating.save()

        self.assertTrue(recompute_staleness(risk_assessment))
        risk_assessment.refresh_from_db()
        self.assertTrue(risk_assessment.stale)

    def test_new_entry_makes_it_stale(self):
        self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(risk_assessment, actor=self.approver)

        self.make_hazard(label="A new hazard")
        self.assertTrue(recompute_staleness(risk_assessment))

    def test_draft_is_never_stale(self):
        self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        self.assertFalse(recompute_staleness(risk_assessment))


class BackgroundTaskTests(RiskFixture):
    """The immediate task backend runs synchronously in tests (conftest.py),
    so these call .enqueue() directly rather than needing a worker."""

    def _basic_hazard_scenario(self):
        hazard = self.make_hazard()
        Rating.objects.create(entry=hazard, method=self.safety_method, severity=2, likelihood=2)
        return hazard

    def test_recompute_all_staleness_checks_only_approved(self):
        self._basic_hazard_scenario()
        RiskAssessment.objects.create(configuration=self.configuration)  # draft, not counted
        approved = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(approved, actor=self.approver)

        checked, newly_stale = recompute_all_staleness()
        self.assertEqual(checked, 1)
        self.assertEqual(newly_stale, 0)

    def test_task_flips_stale_flag(self):
        hazard = self._basic_hazard_scenario()
        risk_assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(risk_assessment, actor=self.approver)

        rating = Rating.objects.get(entry=hazard, method=self.safety_method)
        rating.likelihood = 5
        rating.save()

        result = refresh_staleness_task.enqueue()
        self.assertEqual(result.status, "SUCCESSFUL")
        risk_assessment.refresh_from_db()
        self.assertTrue(risk_assessment.stale)


class ControlModelTests(RiskFixture):
    def test_control_links_threats_and_hazard_causes(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        hazard = self.make_hazard()
        cause = HazardCause.objects.create(hazard=hazard, cause_type=CauseType.HARDWARE_FAILURE)

        control = Control.objects.create(product=self.product, name="Secure boot")
        control.threats.add(threat)
        control.hazard_causes.add(cause)

        self.assertIn(threat, control.threats.all())
        self.assertIn(cause, control.hazard_causes.all())
        self.assertIn(control, threat.controls.all())


class RegisterViewTests(RiskFixture):
    def setUp(self):
        super().setUp()
        self.asset = self.make_asset()
        self.threat = self.make_threat(self.asset)
        ThreatConsequence.objects.create(
            threat=self.threat, impact_category=ImpactCategory.PRIVACY, severity=4
        )
        Rating.objects.create(entry=self.threat, method=self.cia_method, likelihood=4)
        self.hazard = self.make_hazard()
        self.client.force_login(self.editor)
        self.url = f"/risk/configurations/{self.configuration.pk}/"

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_register_lists_entries_with_computed_rating(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wireless eavesdropping")
        self.assertContains(response, "must_treat")  # 4 x 4 = 16 -> high
        self.assertContains(response, "not rated")  # the hazard has no rating yet
        self.assertEqual(response.context["counts"], {"asset": 1, "threat": 1, "hazard": 1})

    def test_filter_by_type_and_search(self):
        response = self.client.get(self.url, {"type": "hazard"})
        self.assertContains(response, "Overheating fire")
        self.assertNotContains(response, "Wireless eavesdropping")
        response = self.client.get(self.url, {"q": "firmware"})
        self.assertContains(response, "Widget firmware")
        self.assertNotContains(response, "Overheating fire")

    def test_delta_replaces_baseline_in_configuration_view(self):
        RiskEntry.objects.create(
            product=self.product,
            entry_type=EntryType.THREAT,
            label="Eavesdropping (TLS)",
            asset=self.asset,
            violates="confidentiality",
            scope_software_release=self.release,
            base_entry=self.threat,
            delta_justification="TLS enforced",
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Eavesdropping (TLS)")
        self.assertContains(response, "Delta · SW release 1.0")
        self.assertNotContains(response, ">Wireless eavesdropping<")

    def test_entry_detail_shows_ratings_and_consequences(self):
        response = self.client.get(f"{self.url}entries/{self.threat.pk}/")
        self.assertContains(response, "Privacy")
        self.assertContains(response, "default-cia-5x5")

    def test_entry_of_another_product_is_404(self):
        other = Product.objects.create(product_family=self.family, name="Other", slug="other")
        foreign = RiskEntry.objects.create(product=other, entry_type=EntryType.ASSET, label="X")
        response = self.client.get(f"{self.url}entries/{foreign.pk}/")
        self.assertEqual(response.status_code, 404)


class EmptyRegisterReadinessTests(RiskFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.editor)
        self.url = f"/risk/configurations/{self.configuration.pk}/"

    def test_empty_register_lists_what_is_configured(self):
        response = self.client.get(self.url)
        self.assertContains(response, "No register entries yet")
        self.assertContains(response, "Target markets set (EU)")
        self.assertContains(response, "A risk method is available")
        self.assertContains(response, "A risk catalog is available")
        self.assertContains(response, "Suggestions from your answers")
        self.assertNotContains(response, "Ask an administrator")

    def test_missing_target_markets_links_to_product(self):
        self.variant.target_markets.clear()
        response = self.client.get(self.url)
        self.assertContains(response, "Open the product")
        self.assertContains(response, f'href="/products/{self.product.pk}/"')

    def test_missing_method_and_catalog_ask_an_administrator(self):
        RequirementPackage.objects.filter(
            kind__in=[PackageKind.METHOD, PackageKind.CATALOG]
        ).update(status=PackageStatus.DRAFT)
        response = self.client.get(self.url)
        self.assertContains(response, "Ask an administrator to import and approve one.", count=2)
        self.assertNotContains(response, "Suggestions from your answers")

    def test_pending_suggestions_are_counted(self):
        Answer.objects.create(
            question_id="has_wireless", value=True, software_release=self.release
        )
        response = self.client.get(self.url)
        self.assertContains(response, "suggested entries are waiting for review")

    def test_filter_with_no_match_is_not_the_empty_state(self):
        self.make_asset()
        response = self.client.get(self.url, {"q": "zzz"})
        self.assertContains(response, "No register entries match the current filter.")
        self.assertNotContains(response, "No register entries yet")


class EntryAuthoringTests(RiskFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.editor)
        self.base = f"/risk/configurations/{self.configuration.pk}/"
        self.create_url = f"{self.base}entries/new/"

    def test_editor_sees_add_button(self):
        response = self.client.get(self.base)
        self.assertContains(response, f'href="{self.create_url}"')

    def test_non_editor_cannot_add(self):
        viewer = User.objects.create_user(username="vic", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=viewer, product_family=self.family)
        self.client.force_login(viewer)
        response = self.client.get(self.base)
        self.assertNotContains(response, f'href="{self.create_url}"')
        response = self.client.post(
            self.create_url, {"entry_type": "asset", "label": "Sneaky asset"}
        )
        self.assertRedirects(response, self.base)
        self.assertFalse(RiskEntry.objects.filter(label="Sneaky asset").exists())

    def test_add_asset(self):
        response = self.client.post(
            self.create_url,
            {"entry_type": "asset", "label": "User data", "description": "Wi-Fi credentials"},
        )
        entry = RiskEntry.objects.get(label="User data")
        self.assertRedirects(response, f"{self.base}entries/{entry.pk}/")
        self.assertEqual(entry.entry_type, EntryType.ASSET)
        self.assertEqual(entry.product, self.product)
        self.assertEqual(entry.suggestion_status, SuggestionStatus.CUSTOM)
        self.assertEqual(entry.created_by, self.editor)
        self.assertTrue(entry.is_baseline)
        self.assertEqual(entry.history.first().history_user, self.editor)

    def test_add_threat_with_asset_and_scope(self):
        asset = self.make_asset()
        self.client.post(
            self.create_url,
            {
                "entry_type": "threat",
                "label": "Firmware tampering",
                "asset": str(asset.pk),
                "violates": "integrity",
                "scope": f"sw:{self.release.pk}",
            },
        )
        threat = RiskEntry.objects.get(label="Firmware tampering")
        self.assertEqual(threat.asset, asset)
        self.assertEqual(threat.violates, "integrity")
        self.assertEqual(threat.scope_software_release, self.release)
        self.assertIsNone(threat.base_entry)

    def test_threat_without_property_is_rejected_and_input_kept(self):
        response = self.client.post(
            self.create_url,
            {"entry_type": "threat", "label": "Half-filled threat", "description": "keep me"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Threats must name the property they violate.")
        self.assertContains(response, 'value="Half-filled threat"')
        self.assertContains(response, "keep me")
        self.assertFalse(RiskEntry.objects.filter(label="Half-filled threat").exists())

    def test_hazard_drops_threat_only_fields(self):
        asset = self.make_asset()
        self.client.post(
            self.create_url,
            {
                "entry_type": "hazard",
                "label": "Electric shock",
                "asset": str(asset.pk),
                "violates": "integrity",
            },
        )
        hazard = RiskEntry.objects.get(label="Electric shock")
        self.assertIsNone(hazard.asset)
        self.assertEqual(hazard.violates, "")

    def test_asset_and_scope_of_another_product_are_rejected(self):
        other = Product.objects.create(product_family=self.family, name="Other", slug="other")
        foreign_asset = RiskEntry.objects.create(
            product=other, entry_type=EntryType.ASSET, label="Foreign"
        )
        foreign_release = SoftwareRelease.objects.create(product=other, version="9.9")
        response = self.client.post(
            self.create_url,
            {
                "entry_type": "threat",
                "label": "Cross-product threat",
                "asset": str(foreign_asset.pk),
                "violates": "integrity",
            },
        )
        self.assertContains(response, "Choose an asset of this product.")
        response = self.client.post(
            self.create_url,
            {"entry_type": "asset", "label": "Cross-scope", "scope": f"sw:{foreign_release.pk}"},
        )
        self.assertContains(response, "Choose a valid scope.")
        self.assertFalse(
            RiskEntry.objects.filter(label__in=["Cross-product threat", "Cross-scope"]).exists()
        )

    def test_violates_choices_come_from_approved_methods(self):
        response = self.client.get(self.create_url)
        values = [c["value"] for c in response.context["violates_choices"]]
        self.assertEqual(values[:3], ["confidentiality", "integrity", "availability"])

    def test_edit_updates_fields_but_not_type(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        url = f"{self.base}entries/{threat.pk}/edit/"
        response = self.client.get(url)
        self.assertContains(response, "Edit threat")
        response = self.client.post(
            url,
            {
                "entry_type": "hazard",
                "label": "Eavesdropping over Wi-Fi",
                "asset": str(asset.pk),
                "violates": "confidentiality",
                "scope": f"hw:{self.variant.pk}",
            },
        )
        self.assertRedirects(response, f"{self.base}entries/{threat.pk}/")
        threat.refresh_from_db()
        self.assertEqual(threat.entry_type, EntryType.THREAT)
        self.assertEqual(threat.label, "Eavesdropping over Wi-Fi")
        self.assertEqual(threat.scope_hardware_variant, self.variant)

    def test_entry_with_deltas_keeps_its_scope(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        self.make_threat(
            asset,
            label="Eavesdropping (TLS)",
            scope_software_release=self.release,
            base_entry=threat,
            delta_justification="TLS enforced",
        )
        url = f"{self.base}entries/{threat.pk}/edit/"
        self.client.post(
            url,
            {
                "label": "Renamed",
                "asset": str(asset.pk),
                "violates": "confidentiality",
                "scope": f"hw:{self.variant.pk}",
            },
        )
        threat.refresh_from_db()
        self.assertEqual(threat.label, "Renamed")
        self.assertTrue(threat.is_baseline)

    def test_detail_shows_edit_link_to_editor_only(self):
        asset = self.make_asset()
        url = f"{self.base}entries/{asset.pk}/"
        self.assertContains(self.client.get(url), f'href="{url}edit/"')
        viewer = User.objects.create_user(username="vic", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=viewer, product_family=self.family)
        self.client.force_login(viewer)
        self.assertNotContains(self.client.get(url), f'href="{url}edit/"')

    def test_save_and_add_another_keeps_type_scope_and_asset(self):
        asset = self.make_asset()
        response = self.client.post(
            self.create_url,
            {
                "entry_type": "threat",
                "label": "Firmware <tampering>",
                "asset": str(asset.pk),
                "violates": "integrity",
                "scope": f"sw:{self.release.pk}",
                "next": "another",
            },
            follow=True,
        )
        threat = RiskEntry.objects.get(label="Firmware <tampering>")
        self.assertEqual(response.request["PATH_INFO"], self.create_url)
        self.assertContains(
            response,
            f'Added <a href="{self.base}entries/{threat.pk}/">Firmware &lt;tampering&gt;</a>',
        )
        self.assertEqual(response.context["entry"].entry_type, EntryType.THREAT)
        self.assertEqual(response.context["entry"].asset, asset)
        self.assertEqual(response.context["scope_value"], f"sw:{self.release.pk}")
        self.assertEqual(response.context["entry"].label, "")

    def test_prefilled_asset_of_another_product_is_ignored(self):
        other = Product.objects.create(product_family=self.family, name="Other", slug="other")
        foreign = RiskEntry.objects.create(product=other, entry_type=EntryType.ASSET, label="F")
        response = self.client.get(self.create_url, {"type": "threat", "asset": foreign.pk})
        self.assertIsNone(response.context["entry"].asset)

    def _post_threat(self, *properties, label="Remote code execution", **extra):
        return self.client.post(
            self.create_url,
            {
                "entry_type": "threat",
                "label": label,
                "asset": str(self.make_asset().pk),
                "violates": list(properties),
                **extra,
            },
        )

    def test_several_properties_add_one_threat_each(self):
        response = self._post_threat("confidentiality", "integrity", "availability")
        threats = RiskEntry.objects.filter(entry_type=EntryType.THREAT).order_by("label")
        self.assertEqual(
            [(t.label, t.violates) for t in threats],
            [
                ("Remote code execution (Availability)", "availability"),
                ("Remote code execution (Confidentiality)", "confidentiality"),
                ("Remote code execution (Integrity)", "integrity"),
            ],
        )
        asset = RiskEntry.objects.get(entry_type=EntryType.ASSET)
        self.assertTrue(all(t.asset == asset and t.is_baseline for t in threats))
        self.assertTrue(all(t.created_by == self.editor for t in threats))
        self.assertRedirects(response, f"{self.base}?type=threat", fetch_redirect_response=False)
        followed = self.client.get(f"{self.base}?type=threat")
        self.assertContains(followed, "Added 3 threats:")

    def test_single_property_keeps_plain_label(self):
        self._post_threat("integrity", label="Firmware tampering")
        self.assertTrue(
            RiskEntry.objects.filter(label="Firmware tampering", violates="integrity").exists()
        )

    def test_split_is_all_or_nothing(self):
        # 190 + " (Confidentiality)" exceeds the 200-character label limit,
        # while 190 + " (Integrity)" does not: nothing may be saved.
        response = self._post_threat("integrity", "confidentiality", label="x" * 190)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RiskEntry.objects.filter(entry_type=EntryType.THREAT).exists())

    def test_unknown_property_is_rejected(self):
        response = self._post_threat("integrity", "telepathy")
        self.assertContains(response, "Choose a property from the risk methods.")
        self.assertFalse(RiskEntry.objects.filter(entry_type=EntryType.THREAT).exists())

    def test_save_and_add_another_with_several_properties(self):
        response = self._post_threat("integrity", "availability", next="another")
        self.assertEqual(RiskEntry.objects.filter(entry_type=EntryType.THREAT).count(), 2)
        self.assertTrue(response["Location"].startswith(self.create_url + "?type=threat"))

    def test_edit_keeps_property_of_a_method_no_longer_approved(self):
        hazard_threat = self.make_threat(
            self.make_asset(), label="Unsafe state", violates="safety"
        )
        RequirementPackage.objects.filter(pk=self.safety_method.pk).update(
            status=PackageStatus.DRAFT
        )
        url = f"{self.base}entries/{hazard_threat.pk}/edit/"
        self.client.post(url, {"label": "Unsafe state renamed", "violates": "safety"})
        hazard_threat.refresh_from_db()
        self.assertEqual(hazard_threat.label, "Unsafe state renamed")
        self.assertEqual(hazard_threat.violates, "safety")


class RatingAndTreatmentAuthoringTests(RiskFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.editor)
        self.asset = self.make_asset()
        self.threat = self.make_threat(self.asset, violates="integrity")
        self.hazard = self.make_hazard()

    def url(self, entry, action=""):
        base = f"/risk/configurations/{self.configuration.pk}/entries/{entry.pk}/"
        return f"{base}{action}/" if action else base

    def test_asset_rating_saves_and_clears_per_property(self):
        self.client.post(
            self.url(self.asset, "asset-rating"),
            {"method": self.cia_method.pk, "confidentiality": "2", "integrity": "4"},
        )
        ratings = {r.property: r.severity for r in self.asset.asset_ratings.all()}
        self.assertEqual(ratings, {"confidentiality": 2, "integrity": 4})
        self.client.post(
            self.url(self.asset, "asset-rating"),
            {"method": self.cia_method.pk, "confidentiality": "", "integrity": "5"},
        )
        ratings = {r.property: r.severity for r in self.asset.asset_ratings.all()}
        self.assertEqual(ratings, {"integrity": 5})

    def test_asset_rating_out_of_scale_is_rejected(self):
        response = self.client.post(
            self.url(self.asset, "asset-rating"),
            {"method": self.cia_method.pk, "integrity": "9"},
            follow=True,
        )
        self.assertContains(response, "Choose a severity between 1 and 5.")
        self.assertFalse(self.asset.asset_ratings.exists())

    def test_consequence_inherits_asset_rating_or_needs_justification(self):
        AssetRating.objects.create(
            entry=self.asset, method=self.cia_method, property="integrity", severity=4
        )
        self.assertContains(self.client.get(self.url(self.threat)), "starts at 4")
        self.client.post(
            self.url(self.threat, "consequences"),
            {"impact_category": "operational", "severity": "4"},
        )
        inherited = self.threat.consequences.get()
        self.assertFalse(inherited.severity_is_override)

        response = self.client.post(
            self.url(self.threat, "consequences"),
            {"impact_category": "financial", "severity": "2"},
            follow=True,
        )
        self.assertContains(response, "needs a justification")
        self.client.post(
            self.url(self.threat, "consequences"),
            {
                "impact_category": "financial",
                "severity": "2",
                "override_justification": "Recall is cheap for this product",
            },
        )
        override = self.threat.consequences.get(impact_category="financial")
        self.assertTrue(override.severity_is_override)

    def test_consequence_links_hazard_only_for_safety_categories(self):
        response = self.client.post(
            self.url(self.threat, "consequences"),
            {"impact_category": "privacy", "severity": "3", "hazard": self.hazard.pk},
            follow=True,
        )
        self.assertContains(response, "Only safety or property-damage consequences")
        self.client.post(
            self.url(self.threat, "consequences"),
            {"impact_category": "safety", "severity": "3", "hazard": self.hazard.pk},
        )
        self.assertEqual(self.threat.consequences.get().hazard, self.hazard)

    def test_consequence_delete(self):
        c = ThreatConsequence.objects.create(
            threat=self.threat, impact_category=ImpactCategory.OPERATIONAL, severity=3
        )
        self.client.post(self.url(self.threat, f"consequences/{c.pk}/delete"))
        self.assertFalse(self.threat.consequences.exists())

    def test_threat_rating_uses_applicable_method_only(self):
        self.client.post(
            self.url(self.threat, "rating"), {"method": self.cia_method.pk, "likelihood": "3"}
        )
        self.assertEqual(Rating.objects.get(entry=self.threat).likelihood, 3)
        response = self.client.post(
            self.url(self.threat, "rating"),
            {"method": self.safety_method.pk, "likelihood": "3"},
            follow=True,
        )
        self.assertContains(response, "doesn&#x27;t apply to this entry")
        self.assertEqual(Rating.objects.filter(entry=self.threat).count(), 1)

    def test_hazard_rated_under_safety_method_with_severity(self):
        detail = self.client.get(self.url(self.hazard))
        rows = [r["method"] for r in detail.context["method_rows"]]
        self.assertEqual(rows, [self.safety_method])
        self.client.post(
            self.url(self.hazard, "rating"),
            {"method": self.safety_method.pk, "severity": "4", "likelihood": "4"},
        )
        result = evaluate_entry_rating(self.hazard, self.safety_method)
        self.assertEqual(result["acceptance"], "must_treat")
        response = self.client.post(
            self.url(self.hazard, "rating"),
            {"method": self.safety_method.pk, "severity": "", "likelihood": "2"},
            follow=True,
        )
        self.assertContains(response, "Hazards must have a directly-rated severity.")

    def test_clearing_likelihood_removes_rating_and_treatment(self):
        Rating.objects.create(entry=self.threat, method=self.cia_method, likelihood=3)
        Treatment.objects.create(
            entry=self.threat, method=self.cia_method, treatment_type=TreatmentType.MITIGATE
        )
        self.client.post(
            self.url(self.threat, "rating"), {"method": self.cia_method.pk, "likelihood": ""}
        )
        self.assertFalse(Rating.objects.filter(entry=self.threat).exists())
        self.assertFalse(Treatment.objects.filter(entry=self.threat).exists())

    def test_treatment_needs_a_rating_first(self):
        response = self.client.post(
            self.url(self.threat, "treatment"),
            {"method": self.cia_method.pk, "treatment_type": "mitigate"},
            follow=True,
        )
        self.assertContains(response, "Rate the entry under default-cia-5x5 first.")
        self.assertFalse(Treatment.objects.exists())

    def test_treatment_mitigated_to_acceptable_needs_no_justification(self):
        Rating.objects.create(entry=self.threat, method=self.cia_method, likelihood=4)
        self.client.post(
            self.url(self.threat, "treatment"),
            {
                "method": self.cia_method.pk,
                "treatment_type": "mitigate",
                "residual_severity": "2",
                "residual_likelihood": "2",
            },
        )
        treatment = Treatment.objects.get(entry=self.threat)
        self.assertEqual(evaluate_residual_rating(treatment)["acceptance"], "accept")
        self.assertEqual(treatment.history.first().history_user, self.editor)

    def test_accept_or_justify_level_residual_needs_justification(self):
        Rating.objects.create(entry=self.threat, method=self.cia_method, likelihood=4)
        for treatment_type, sev, lik in (("accept", "", ""), ("mitigate", "3", "3")):
            response = self.client.post(
                self.url(self.threat, "treatment"),
                {
                    "method": self.cia_method.pk,
                    "treatment_type": treatment_type,
                    "residual_severity": sev,
                    "residual_likelihood": lik,
                },
                follow=True,
            )
            self.assertContains(response, "Explain this treatment decision")
        self.assertFalse(Treatment.objects.exists())

    def test_residual_needs_both_values(self):
        Rating.objects.create(entry=self.threat, method=self.cia_method, likelihood=4)
        response = self.client.post(
            self.url(self.threat, "treatment"),
            {
                "method": self.cia_method.pk,
                "treatment_type": "mitigate",
                "residual_severity": "2",
                "residual_likelihood": "",
            },
            follow=True,
        )
        self.assertContains(response, "Give both residual severity and likelihood")

    def test_create_link_status_and_unlink_control(self):
        self.client.post(
            self.url(self.threat, "controls"), {"name": "Secure boot", "status": "planned"}
        )
        control = Control.objects.get(name="Secure boot")
        self.assertEqual(list(control.threats.all()), [self.threat])
        self.client.post(
            self.url(self.threat, f"controls/{control.pk}/status"), {"status": "implemented"}
        )
        control.refresh_from_db()
        self.assertEqual(control.status, "implemented")
        other = self.make_threat(self.asset, label="Rollback", violates="integrity")
        self.client.post(self.url(other, "controls"), {"control": control.pk})
        self.assertEqual(control.threats.count(), 2)
        self.client.post(self.url(self.threat, f"controls/{control.pk}/unlink"))
        self.assertEqual(list(control.threats.all()), [other])

    def test_control_of_another_product_cannot_be_linked(self):
        other = Product.objects.create(product_family=self.family, name="Other", slug="other")
        foreign = Control.objects.create(product=other, name="Foreign")
        response = self.client.post(self.url(self.threat, "controls"), {"control": foreign.pk})
        self.assertEqual(response.status_code, 404)

    def test_viewer_cannot_change_anything(self):
        viewer = User.objects.create_user(username="vic", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=viewer, product_family=self.family)
        self.client.force_login(viewer)
        self.client.post(
            self.url(self.threat, "rating"), {"method": self.cia_method.pk, "likelihood": "3"}
        )
        self.client.post(self.url(self.threat, "controls"), {"name": "Sneaky"})
        self.assertFalse(Rating.objects.exists())
        self.assertFalse(Control.objects.exists())
        page = self.client.get(self.url(self.threat))
        self.assertNotContains(page, "Save rating")

    def test_get_is_not_allowed_on_actions(self):
        response = self.client.get(self.url(self.threat, "rating"))
        self.assertEqual(response.status_code, 405)

    def test_delete_entry_confirms_then_deletes_and_unlinks(self):
        Rating.objects.create(entry=self.threat, method=self.cia_method, likelihood=3)
        url = self.url(self.asset, "delete")
        page = self.client.get(url)
        self.assertContains(page, "no longer targets an asset")
        self.assertTrue(RiskEntry.objects.filter(pk=self.asset.pk).exists())
        response = self.client.post(url)
        self.assertRedirects(response, f"/risk/configurations/{self.configuration.pk}/")
        self.assertFalse(RiskEntry.objects.filter(pk=self.asset.pk).exists())
        self.threat.refresh_from_db()
        self.assertIsNone(self.threat.asset)
        self.client.post(self.url(self.threat, "delete"))
        self.assertFalse(Rating.objects.exists())

    def test_entry_with_deltas_cannot_be_deleted(self):
        self.make_threat(
            self.asset,
            label="Tampering (signed)",
            violates="integrity",
            scope_software_release=self.release,
            base_entry=self.threat,
            delta_justification="Signed updates",
        )
        response = self.client.post(self.url(self.threat, "delete"), follow=True)
        self.assertContains(response, "delete those first")
        self.assertTrue(RiskEntry.objects.filter(pk=self.threat.pk).exists())

    def test_viewer_cannot_delete(self):
        viewer = User.objects.create_user(username="vic", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=viewer, product_family=self.family)
        self.client.force_login(viewer)
        self.client.post(self.url(self.hazard, "delete"))
        self.assertTrue(RiskEntry.objects.filter(pk=self.hazard.pk).exists())


class HazardCauseAuthoringTests(RiskFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.editor)
        self.hazard = self.make_hazard()
        self.threat = self.make_threat(self.make_asset(), violates="integrity")
        self.base = f"/risk/configurations/{self.configuration.pk}/entries/{self.hazard.pk}/"

    def test_add_and_remove_cause(self):
        self.client.post(
            f"{self.base}causes/",
            {"cause_type": "hardware_failure", "description": "Thermal fuse fails closed"},
        )
        cause = self.hazard.causes.get()
        self.assertEqual(cause.description, "Thermal fuse fails closed")
        self.client.post(f"{self.base}causes/{cause.pk}/delete/")
        self.assertFalse(self.hazard.causes.exists())

    def test_cyberattack_cause_needs_a_threat_of_the_product(self):
        response = self.client.post(
            f"{self.base}causes/", {"cause_type": "cyberattack"}, follow=True
        )
        self.assertContains(response, "should link the responsible threat entry")
        self.client.post(
            f"{self.base}causes/", {"cause_type": "cyberattack", "threat": self.threat.pk}
        )
        self.assertEqual(self.hazard.causes.get().threat, self.threat)

    def test_threat_is_ignored_for_non_cyber_causes(self):
        self.client.post(
            f"{self.base}causes/", {"cause_type": "software_fault", "threat": self.threat.pk}
        )
        self.assertIsNone(self.hazard.causes.get().threat)

    def test_controls_link_per_cause(self):
        cause = HazardCause.objects.create(hazard=self.hazard, cause_type="hardware_failure")
        self.client.post(
            f"{self.base}controls/",
            {"cause": cause.pk, "name": "Thermal fuse", "status": "planned"},
        )
        control = Control.objects.get(name="Thermal fuse")
        self.assertEqual(list(control.hazard_causes.all()), [cause])
        self.assertFalse(control.threats.exists())
        self.client.post(f"{self.base}controls/{control.pk}/unlink/", {"cause": cause.pk})
        self.assertFalse(control.hazard_causes.exists())

    def test_cause_of_another_hazard_is_refused(self):
        other = self.make_hazard(label="Electric shock")
        foreign = HazardCause.objects.create(hazard=other, cause_type="hardware_failure")
        response = self.client.post(
            f"{self.base}controls/", {"cause": foreign.pk, "name": "Sneaky"}, follow=True
        )
        self.assertContains(response, "one of a hazard&#x27;s causes")
        self.assertFalse(Control.objects.exists())

    def test_catalog_hazard_prompts_for_missing_cyberattack_cause(self):
        catalog_hazard = accept_suggestion(self.product, self.catalog, "overheating_fire")
        url = f"/risk/configurations/{self.configuration.pk}/entries/{catalog_hazard.pk}/"
        self.assertContains(self.client.get(url), "The catalog lists a cyberattack")
        HazardCause.objects.create(
            hazard=catalog_hazard, cause_type="cyberattack", threat=self.threat
        )
        self.assertNotContains(self.client.get(url), "The catalog lists a cyberattack")


class SuggestionReviewTests(RiskFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.editor)
        Answer.objects.create(
            question_id="has_wireless", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="rated_power_watts", value=100, hardware_revision=self.revision
        )
        Answer.objects.create(
            question_id="has_power_source", value=True, hardware_revision=self.revision
        )
        Answer.objects.create(question_id="is_toy_widget", value=False, product=self.product)
        self.url = f"/risk/configurations/{self.configuration.pk}/suggestions/"
        self.key = f"{self.catalog.pk}:unauthorized_wireless_access"

    def test_page_lists_pending_and_register_links_to_it(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Unauthorised access via wireless interface")
        self.assertContains(response, "Overheating leading to fire")
        register = self.client.get(f"/risk/configurations/{self.configuration.pk}/")
        self.assertContains(register, f'href="{self.url}"')

    def test_accept_threat_with_asset_and_suggested_controls(self):
        asset = self.make_asset()
        existing = Control.objects.create(product=self.product, name="Secure boot")
        self.client.post(
            f"{self.url}accept/", {"suggestion": self.key, "asset": asset.pk, "add_controls": "1"}
        )
        entry = RiskEntry.objects.get(source_catalog_entry_id="unauthorized_wireless_access")
        self.assertEqual(entry.suggestion_status, SuggestionStatus.ACCEPTED)
        self.assertEqual(entry.asset, asset)
        self.assertEqual(entry.created_by, self.editor)
        self.assertEqual(
            sorted(entry.controls.values_list("name", flat=True)),
            ["Authenticate wireless clients", "Secure boot"],
        )
        self.assertIn(existing, entry.controls.all())  # reused, not duplicated
        self.assertEqual(Control.objects.filter(name="Secure boot").count(), 1)
        pending = self.client.get(self.url).context["pending"]
        self.assertNotIn(self.key, [s["key"] for s in pending])

    def test_accept_without_controls(self):
        self.client.post(f"{self.url}accept/", {"suggestion": self.key})
        entry = RiskEntry.objects.get(source_catalog_entry_id="unauthorized_wireless_access")
        self.assertFalse(entry.controls.exists())

    def test_dismiss_needs_reason_and_restore_accepts(self):
        response = self.client.post(
            f"{self.url}dismiss/", {"suggestion": self.key, "reason": ""}, follow=True
        )
        self.assertContains(response, "Give a reason")
        self.assertFalse(RiskEntry.objects.exists())
        self.client.post(
            f"{self.url}dismiss/", {"suggestion": self.key, "reason": "No radio in this variant"}
        )
        entry = RiskEntry.objects.get()
        self.assertEqual(entry.suggestion_status, SuggestionStatus.DISMISSED)
        page = self.client.get(self.url)
        self.assertContains(page, "No radio in this variant")
        self.client.post(f"{self.url}{entry.pk}/restore/")
        entry.refresh_from_db()
        self.assertEqual(entry.suggestion_status, SuggestionStatus.ACCEPTED)
        self.assertEqual(entry.dismissal_reason, "")

    def test_untriggered_or_decided_suggestion_is_refused(self):
        response = self.client.post(
            f"{self.url}accept/",
            {"suggestion": f"{self.catalog.pk}:no_such_entry"},
            follow=True,
        )
        self.assertContains(response, "no longer pending")
        self.client.post(f"{self.url}accept/", {"suggestion": self.key})
        response = self.client.post(f"{self.url}accept/", {"suggestion": self.key}, follow=True)
        self.assertContains(response, "no longer pending")
        self.assertEqual(RiskEntry.objects.count(), 1)

    def test_viewer_sees_but_cannot_act(self):
        viewer = User.objects.create_user(username="vic", password="x")
        RoleAssignment.objects.create(role=Role.VIEWER, user=viewer, product_family=self.family)
        self.client.force_login(viewer)
        page = self.client.get(self.url)
        self.assertContains(page, "Unauthorised access via wireless interface")
        self.assertNotContains(page, "Dismiss…")
        self.client.post(f"{self.url}accept/", {"suggestion": self.key})
        self.assertFalse(RiskEntry.objects.exists())

    def test_readiness_links_to_review(self):
        response = self.client.get(f"/risk/configurations/{self.configuration.pk}/")
        self.assertContains(response, "Review suggestions")

    def test_catalog_hazard_lists_suggested_controls_until_linked(self):
        catalog_hazard = accept_suggestion(self.product, self.catalog, "overheating_fire")
        url = f"/risk/configurations/{self.configuration.pk}/entries/{catalog_hazard.pk}/"
        response = self.client.get(url)
        self.assertEqual(
            response.context["catalog_controls"], ["Thermal fuse", "Firmware power limiting"]
        )
        cause = catalog_hazard.causes.get()  # hardware_failure, created on accept
        Control.objects.create(product=self.product, name="Thermal fuse").hazard_causes.add(cause)
        response = self.client.get(url)
        self.assertEqual(response.context["catalog_controls"], ["Firmware power limiting"])
