import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.accounts.models import User
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
