from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import RiskEntry, Treatment
from .portfolio import age_chart, last_change, portfolio_metrics
from .test_metrics import MetricsFixture


class AgeChartTests(MetricsFixture):
    def test_days_fall_into_buckets_split_by_class(self):
        rows = age_chart(
            [
                (0, "must_treat"),
                (30, "accept"),
                (31, "justify"),
                (181, "unrated"),
                (400, "unrated"),
            ]
        )
        self.assertEqual([r["total"] for r in rows], [2, 1, 0, 2])
        self.assertEqual(rows[0]["counts"]["must_treat"], 1)
        self.assertEqual(rows[3]["counts"]["unrated"], 2)
        self.assertEqual([r["width"] for r in rows], [100, 50, 0, 100])
        self.assertEqual(rows[2]["segments"], [])

    def test_empty_chart_has_no_width(self):
        self.assertEqual({r["width"] for r in age_chart([])}, {0})


class PortfolioMetricsTests(MetricsFixture):
    def metrics(self):
        return portfolio_metrics([self.product])

    def age(self, entry, days):
        RiskEntry.objects.filter(pk=entry.pk).update(
            created_at=timezone.now() - timedelta(days=days),
            updated_at=timezone.now() - timedelta(days=days),
        )

    def test_empty_portfolio(self):
        m = portfolio_metrics([])
        self.assertEqual((m["rateable"], m["product_count"], m["oldest"]), (0, 0, []))
        self.assertEqual(m["heatmaps"], [])

    def test_open_entry_ages_from_when_it_was_added(self):
        hazard = self.rated_hazard()
        self.age(hazard, 200)
        m = self.metrics()
        self.assertEqual(m["open_total"], 1)
        self.assertEqual(m["open_chart"][3]["counts"]["must_treat"], 1)
        self.assertEqual(m["oldest"][0]["days"], 200)
        self.assertEqual(m["products"][0]["oldest_open"], 200)

    def test_mitigated_entry_is_not_open(self):
        hazard = self.rated_hazard()
        self.treat(hazard, kind="accept", residual=(1, 1), justification="Negligible")
        m = self.metrics()
        self.assertEqual(m["open_total"], 0)
        self.assertEqual(m["oldest"], [])

    def test_unrated_entry_counts_as_open(self):
        self.make_hazard("Unrated")
        m = self.metrics()
        self.assertEqual(m["open_chart"][0]["counts"]["unrated"], 1)

    def test_last_change_includes_the_treatment(self):
        hazard = self.rated_hazard()
        self.age(hazard, 300)
        treatment = self.treat(hazard, kind="accept", residual=(1, 1), justification="x")
        hazard = RiskEntry.objects.get(pk=hazard.pk)
        self.assertEqual(last_change(hazard), Treatment.objects.get(pk=treatment.pk).updated_at)
        self.assertEqual(self.metrics()["changed_chart"][0]["total"], 1)

    def test_matrices_are_per_method_and_label_the_product(self):
        self.rated_hazard("Overheating")
        m = self.metrics()
        self.assertEqual([g["method"].source for g in m["heatmaps"]], ["demo-safety-5x5"])
        cell = next(c for row in m["heatmaps"][0]["rows"] for c in row["cells"] if c["inherent"])
        self.assertEqual(cell["inherent"][0].product_name, "TempSense")


class PortfolioPageTests(MetricsFixture):
    def test_requires_login(self):
        response = self.client.get(reverse("core:risk_overview"))
        self.assertEqual(response.status_code, 302)

    def test_page_shows_matrices_and_ageing(self):
        self.rated_hazard("Overheating")
        self.client.force_login(self.editor)
        response = self.client.get(reverse("core:risk_overview"))
        self.assertContains(response, "Risk matrices")
        self.assertContains(response, "How long risks have waited")
        self.assertContains(response, "Open the longest")
        self.assertContains(response, "TempSense: Overheating")
        self.assertContains(response, reverse("products:product_detail", args=[self.product.pk]))

    def test_empty_state(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("core:risk_overview"))
        self.assertContains(response, "No threats or hazards")

    def test_only_products_the_user_can_see(self):
        self.rated_hazard("Overheating")
        outsider = get_user_model().objects.create_user("zed", password="x")
        self.client.force_login(outsider)
        response = self.client.get(reverse("core:risk_overview"))
        self.assertNotContains(response, "Overheating")
        self.assertEqual(response.context["m"]["product_count"], 0)

    def test_nav_has_a_risk_link(self):
        self.client.force_login(self.editor)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("core:risk_overview"))


class TouchTests(MetricsFixture):
    def test_saving_a_rating_stamps_the_entry(self):
        hazard = self.make_hazard("Overheating")
        RiskEntry.objects.filter(pk=hazard.pk).update(
            updated_at=timezone.now() - timedelta(days=100)
        )
        self.client.force_login(self.editor)
        self.client.post(
            reverse("risk:rating_save", args=[self.configuration.pk, hazard.pk]),
            {"method": self.safety_method.pk, "likelihood": 3, "severity": 3},
        )
        hazard.refresh_from_db()
        self.assertLess((timezone.now() - hazard.updated_at).days, 1)
