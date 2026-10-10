from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from . import tests as base
from .approval import approve_risk_assessment
from .metrics import governance, product_metrics, register_metrics, risk_summary
from .models import (
    AssetRating,
    Control,
    ControlStatus,
    EntryType,
    Rating,
    RiskAssessment,
    RiskEntry,
    ThreatConsequence,
    Treatment,
)


class MetricsFixture(base.RiskFixture):
    def rated_hazard(self, label="Overheating", severity=5, likelihood=4, method=None):
        hazard = self.make_hazard(label)
        Rating.objects.create(
            entry=hazard,
            method=method or self.safety_method,
            severity=severity,
            likelihood=likelihood,
        )
        return hazard

    def treat(self, entry, *, kind="mitigate", residual=(1, 1), justification="", method=None):
        return Treatment.objects.create(
            entry=entry,
            method=method or self.safety_method,
            treatment_type=kind,
            residual_severity=residual[0],
            residual_likelihood=residual[1],
            justification=justification,
        )

    def metrics(self):
        return register_metrics(self.configuration)


class ExposureTests(MetricsFixture):
    def test_empty_register(self):
        m = self.metrics()
        self.assertEqual(m["total"], 0)
        self.assertEqual(m["completeness"]["rateable"], 0)
        self.assertEqual(m["exposure"]["open_must_treat"], 0)
        self.assertEqual(m["acceptable"], (0, 0))
        self.assertEqual(m["heatmaps"], [])
        self.assertEqual(m["top"], [])

    def test_unrated_entry_is_counted_as_unrated_not_as_a_class(self):
        self.make_hazard()
        m = self.metrics()
        self.assertEqual(m["completeness"]["unrated"], 1)
        self.assertEqual(m["exposure"]["inherent"]["unrated"], 1)
        self.assertEqual(m["exposure"]["residual"]["unrated"], 1)
        self.assertEqual(m["exposure"]["open_must_treat"], 0)

    def test_untreated_must_treat_entry_is_open(self):
        self.rated_hazard()
        m = self.metrics()
        self.assertEqual(m["exposure"]["inherent"]["must_treat"], 1)
        self.assertEqual(m["exposure"]["residual"]["must_treat"], 1)
        self.assertEqual(m["exposure"]["open_must_treat"], 1)
        self.assertEqual(m["completeness"]["untreated"], 1)
        self.assertEqual(m["completeness"]["rated"], 1)

    def test_mitigation_only_counts_once_controls_are_in_place(self):
        hazard = self.rated_hazard()
        self.treat(hazard)
        m = self.metrics()
        self.assertEqual(m["exposure"]["open_must_treat"], 1)
        self.assertEqual(m["treatment"]["mitigation"]["no_controls"], 1)
        self.assertEqual(m["completeness"]["untreated"], 0)

        cause = hazard.causes.create(cause_type="hardware_failure")
        control = Control.objects.create(product=self.product, name="Thermal fuse")
        control.hazard_causes.add(cause)
        m = self.metrics()
        self.assertEqual(m["treatment"]["mitigation"]["planned"], 1)
        self.assertEqual(m["exposure"]["open_must_treat"], 1)

        control.status = ControlStatus.IMPLEMENTED
        control.save()
        m = self.metrics()
        self.assertEqual(m["treatment"]["mitigation"]["in_place"], 1)
        self.assertEqual(m["exposure"]["residual"]["accept"], 1)
        self.assertEqual(m["exposure"]["open_must_treat"], 0)
        self.assertEqual(m["exposure"]["reduced"], 1)
        self.assertEqual(m["acceptable"], (1, 1))

    def test_treatment_without_residual_rating_does_not_reduce_risk(self):
        hazard = self.rated_hazard()
        Treatment.objects.create(
            entry=hazard,
            method=self.safety_method,
            treatment_type="accept",
            justification="x",
        )
        m = self.metrics()
        self.assertEqual(m["exposure"]["open_must_treat"], 1)
        self.assertEqual(m["completeness"]["untreated"], 0)
        self.assertEqual(m["acceptable"], (0, 1))

    def test_entry_takes_its_worst_class_across_methods(self):
        hazard = self.rated_hazard()
        Rating.objects.create(entry=hazard, method=self.cia_method, severity=1, likelihood=1)
        m = self.metrics()
        self.assertEqual(m["exposure"]["inherent"]["must_treat"], 1)
        self.assertEqual(sum(m["exposure"]["inherent"].values()), 1)

    def test_threat_severity_comes_from_its_worst_consequence(self):
        asset = self.make_asset()
        threat = self.make_threat(asset)
        Rating.objects.create(entry=threat, method=self.cia_method, likelihood=3)
        m = self.metrics()
        # Rated but no consequence yet: severity cannot be derived.
        self.assertEqual(m["completeness"]["incomplete"], 1)
        self.assertEqual(m["completeness"]["threats_without_consequence"], 1)
        self.assertEqual(m["exposure"]["inherent"]["unrated"], 1)

        ThreatConsequence.objects.create(threat=threat, impact_category="operational", severity=2)
        ThreatConsequence.objects.create(threat=threat, impact_category="financial", severity=3)
        m = self.metrics()
        self.assertEqual(m["completeness"]["incomplete"], 0)
        self.assertEqual(m["exposure"]["inherent"]["justify"], 1)  # 3 x 3 = 9: medium

    def test_top_list_orders_by_class_then_severity(self):
        self.rated_hazard("Medium", severity=3, likelihood=3)
        self.rated_hazard("Worse", severity=5, likelihood=4)
        self.rated_hazard("Worst", severity=5, likelihood=5)
        self.rated_hazard("Low", severity=1, likelihood=1)
        top = self.metrics()["top"]
        self.assertEqual([t["entry"].label for t in top], ["Worst", "Worse", "Medium"])
        self.assertEqual(top[0]["class"], "must_treat")
        self.assertEqual(top[2]["class"], "justify")

    def test_heatmap_places_entries_before_and_after_treatment(self):
        hazard = self.rated_hazard()
        self.treat(hazard, kind="accept", residual=(2, 2), justification="Low exposure")
        grid = self.metrics()["heatmaps"][0]
        self.assertEqual(grid["method"], self.safety_method)
        self.assertEqual([r["severity"] for r in grid["rows"]], [5, 4, 3, 2, 1])
        cells = {(c["severity"], c["likelihood"]): c for r in grid["rows"] for c in r["cells"]}
        self.assertEqual(cells[(5, 4)]["inherent"], [hazard])
        self.assertEqual(cells[(5, 4)]["residual"], [])
        self.assertEqual(cells[(2, 2)]["residual"], [hazard])
        self.assertEqual(cells[(5, 4)]["acceptance"], "must_treat")

    def test_missing_justification_is_counted(self):
        hazard = self.rated_hazard()
        self.treat(hazard, kind="accept", residual=(2, 2), justification="")
        self.assertEqual(self.metrics()["treatment"]["missing_justification"], 1)
        Treatment.objects.update(justification="Low exposure")
        self.assertEqual(self.metrics()["treatment"]["missing_justification"], 0)


class CompletenessTests(MetricsFixture):
    def test_unrated_assets_and_pending_counts(self):
        asset = self.make_asset()
        self.make_asset("Rated asset")
        AssetRating.objects.create(
            entry=RiskEntry.objects.get(label="Rated asset"),
            method=self.cia_method,
            property="confidentiality",
            severity=3,
        )
        c = self.metrics()["completeness"]
        self.assertEqual(c["assets"], 2)
        self.assertEqual(c["assets_unrated"], 1)
        self.assertEqual(c["rateable"], 0)
        self.assertEqual(asset.entry_type, EntryType.ASSET)


class ControlMetricTests(MetricsFixture):
    def test_verified_control_needs_current_evidence(self):
        hazard = self.rated_hazard()
        cause = hazard.causes.create(cause_type="hardware_failure")
        control = Control.objects.create(
            product=self.product, name="Fuse", status=ControlStatus.VERIFIED
        )
        control.hazard_causes.add(cause)
        self.assertEqual(self.metrics()["controls"]["verified_without_evidence"], 1)
        self.assertEqual(self.metrics()["controls"]["by_status"]["verified"], 1)

    def test_unlinked_controls_only_show_at_product_level(self):
        Control.objects.create(product=self.product, name="Orphan")
        self.assertEqual(self.metrics()["controls"]["total"], 0)
        rolled = product_metrics(self.product)["controls"]
        self.assertEqual(rolled["total"], 1)
        self.assertEqual(rolled["unlinked"], 1)


class GovernanceTests(MetricsFixture):
    def test_no_risk_assessment(self):
        self.assertEqual(governance(self.configuration)["status"], "none")

    def test_draft_then_approved_then_stale(self):
        assessment = RiskAssessment.objects.create(configuration=self.configuration)
        self.assertEqual(governance(self.configuration)["label"], "Draft")
        approve_risk_assessment(assessment, actor=self.approver)
        g = governance(self.configuration)
        self.assertEqual(g["label"], "Approved")
        self.assertEqual(g["age_days"], 0)
        RiskAssessment.objects.update(stale=True, approved_at=timezone.now() - timedelta(days=40))
        g = governance(self.configuration)
        self.assertEqual(g["label"], "Approved, stale")
        self.assertEqual(g["age_days"], 40)

    def test_method_version_behind_is_reported(self):
        hazard = self.rated_hazard()
        assessment = RiskAssessment.objects.create(configuration=self.configuration)
        approve_risk_assessment(assessment, actor=self.approver)
        self.assertEqual(governance(self.configuration)["versions_behind"], [])
        snapshot = RiskAssessment.objects.get().snapshot
        snapshot["methods"] = [["demo-safety-5x5", "0.9.0"]]
        RiskAssessment.objects.update(snapshot=snapshot)
        behind = governance(self.configuration)["versions_behind"]
        self.assertEqual(
            behind, [{"source": "demo-safety-5x5", "used": "0.9.0", "latest": "1.0.0"}]
        )
        self.assertTrue(hazard.pk)


class ProductRollUpTests(MetricsFixture):
    def test_entries_count_once_across_configurations(self):
        other_release = base.SoftwareRelease.objects.create(product=self.product, version="2.0")
        base.Configuration.objects.create(
            name="TempSense EU 2.0",
            hardware_revision=self.revision,
            software_release=other_release,
        )
        self.rated_hazard()
        m = product_metrics(self.product)
        self.assertEqual(m["completeness"]["rateable"], 1)
        self.assertEqual(m["exposure"]["open_must_treat"], 1)
        self.assertEqual(len(m["configurations"]), 2)
        self.assertEqual({r["exposure"]["open_must_treat"] for r in m["configurations"]}, {1})

    def test_release_scoped_entry_is_open_only_where_it_applies(self):
        other_release = base.SoftwareRelease.objects.create(product=self.product, version="2.0")
        other = base.Configuration.objects.create(
            name="TempSense EU 2.0",
            hardware_revision=self.revision,
            software_release=other_release,
        )
        hazard = self.make_hazard("Only in 2.0", scope_software_release=other_release)
        Rating.objects.create(entry=hazard, method=self.safety_method, severity=5, likelihood=5)
        rows = {r["configuration"].pk: r for r in product_metrics(self.product)["configurations"]}
        self.assertEqual(rows[self.configuration.pk]["exposure"]["open_must_treat"], 0)
        self.assertEqual(rows[other.pk]["exposure"]["open_must_treat"], 1)
        self.assertEqual(product_metrics(self.product)["exposure"]["open_must_treat"], 1)

    def test_summary_matches_roll_up(self):
        self.rated_hazard()
        self.rated_hazard("Unrated too")
        Rating.objects.filter(entry__label="Unrated too").delete()
        summary = risk_summary(self.product)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["open_must_treat"], 1)
        self.assertEqual(summary["unrated"], 1)
        self.assertEqual(summary["acceptable"], 0)


class PageTests(MetricsFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.editor)

    def test_register_page_shows_status(self):
        hazard = self.rated_hazard("Overheating fire")
        self.treat(hazard, kind="accept", residual=(2, 2), justification="Low exposure")
        response = self.client.get(reverse("risk:register", args=[self.configuration.pk]))
        self.assertContains(response, "Risk status")
        self.assertContains(response, "still must treat")
        self.assertContains(response, "Before treatment")
        self.assertContains(response, "Risk matrices")
        self.assertContains(response, "demo-safety-5x5")
        self.assertContains(response, 'class="heatmap-cell class-must_treat"')

    def test_status_ignores_the_register_filter(self):
        self.rated_hazard("Overheating fire")
        response = self.client.get(
            reverse("risk:register", args=[self.configuration.pk]) + "?q=nothing-matches"
        )
        self.assertEqual(response.context["metrics"]["exposure"]["open_must_treat"], 1)

    def test_empty_register_page_still_renders(self):
        response = self.client.get(reverse("risk:register", args=[self.configuration.pk]))
        self.assertContains(response, "No ratings yet")

    def test_product_page_has_a_risk_tab_with_one_row_per_configuration(self):
        self.rated_hazard()
        response = self.client.get(reverse("products:product_detail", args=[self.product.pk]))
        self.assertContains(response, "Risk status")
        self.assertContains(response, "By configuration")
        self.assertContains(response, self.configuration.name)

    def test_compliance_overview_lists_open_and_unrated_counts(self):
        self.rated_hazard()
        self.make_hazard("Unrated")
        response = self.client.get(reverse("core:compliance"))
        row = response.context["rows"][0]
        self.assertEqual((row["must_treat"], row["unrated"]), (1, 1))
        self.assertEqual(response.context["totals"]["must_treat"], 1)
        self.assertContains(response, "Still must treat")
