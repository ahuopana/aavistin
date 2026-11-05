"""End-to-end: risk status on the register, the product page and the
Compliance Overview. The register is seeded through the ORM; everything the
user does goes through the real pages."""

import json
import os
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from playwright.sync_api import expect

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
from apps.risk.models import Control, EntryType, Rating, RiskEntry, Treatment

from .test_assessment_journey import open_tab, sign_in


def _method(name):
    path = Path(settings.BASE_DIR) / "packages" / name / "1.0.0.json"
    package = import_package(
        json.loads(path.read_text()), kind=PackageKind.METHOD, is_official=True
    )
    approve_package(package)
    return package


def test_risk_status_journey(page, live_server, world):
    page_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    method = _method("demo-safety-5x5")

    product = Product.objects.create(product_family=world["family"], name="Gateway", slug="gw")
    variant = HardwareVariant.objects.create(product=product, name="Global", slug="global")
    variant.target_markets.set(TargetMarket.objects.filter(code="EU"))
    revision = HardwareRevision.objects.create(hardware_variant=variant, label="A")
    release = SoftwareRelease.objects.create(product=product, name="Firmware", version="2.0")
    configuration = Configuration.objects.create(
        name="Gateway EU 2.0", hardware_revision=revision, software_release=release
    )

    def hazard(label, severity, likelihood):
        entry = RiskEntry.objects.create(product=product, entry_type=EntryType.HAZARD, label=label)
        Rating.objects.create(entry=entry, method=method, severity=severity, likelihood=likelihood)
        return entry

    fire = hazard("Overheating fire", 5, 4)
    hazard("Electric shock", 5, 5)
    Treatment.objects.create(
        entry=fire,
        method=method,
        treatment_type="mitigate",
        residual_severity=2,
        residual_likelihood=2,
    )
    Control.objects.create(product=product, name="Thermal fuse", status="implemented")

    sign_in(page, live_server, "edna", world["password"])

    # --- Register: status above the list --------------------------------------------
    page.goto(f"{live_server.url}{reverse('risk:register', args=[configuration.pk])}")
    status = page.locator(".risk-status")
    expect(status.get_by_text("still must treat")).to_be_visible()
    # The mitigation has no controls linked yet, so both hazards are still open.
    expect(status.locator(".risk-stat-alert .risk-stat-value").first).to_have_text("2")
    expect(status.get_by_text("Needs attention first")).to_be_visible()
    status.get_by_text("Risk matrices").click()
    expect(status.locator(".heatmap-cell.class-must_treat").first).to_be_visible()
    expect(status.locator(".heatmap-count").first).to_be_visible()

    # --- Product page: a Risk status tab with one row per configuration --------------
    page.goto(f"{live_server.url}{reverse('products:product_detail', args=[product.pk])}")
    open_tab(page, "Risk status")
    expect(page.get_by_role("heading", name="By configuration")).to_be_visible()
    row = page.locator(".risk-product-table tr", has_text="Gateway EU 2.0")
    expect(row).to_contain_text("No risk assessment")
    row.get_by_role("link", name="Gateway EU 2.0").click()
    expect(page.get_by_role("heading", name="Risk register")).to_be_visible()

    # --- Compliance Overview ----------------------------------------------------------
    page.goto(f"{live_server.url}{reverse('core:compliance')}")
    expect(page.get_by_role("columnheader", name="Still must treat")).to_be_visible()
    expect(page.locator("tr", has_text="Gateway")).to_contain_text("2")

    # --- Portfolio Risk page: matrices and ageing --------------------------------------
    page.get_by_role("link", name="Risk", exact=True).click()
    expect(page.get_by_role("heading", name="Risk", exact=True)).to_be_visible()
    expect(page.locator(".heatmap-cell.class-must_treat").first).to_be_visible()
    expect(page.get_by_role("heading", name="How long risks have waited")).to_be_visible()
    expect(page.locator(".age-row", has_text="30 days or less").first).to_contain_text("2")
    expect(page.locator("tr", has_text="Gateway").first).to_be_visible()
    shot = os.environ.get("AAVISTIN_SHOT")
    if shot:
        page.screenshot(path=shot, full_page=True)

    assert page_errors == []
