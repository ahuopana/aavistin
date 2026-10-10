"""End-to-end: markets on a software release, the EU CRA questionnaire with
date questions, and dated requirements on the assessment page.

The product hierarchy and packages are seeded through the ORM; everything
the user does goes through the real UI. The assessment date is pinned so the
"not in force yet" list does not change meaning after 11 December 2027.
"""

import json
import re
from datetime import date
from pathlib import Path
from unittest import mock

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

from .test_assessment_journey import answer, form_for, open_tab, sign_in, submit


def _approve(path, **kwargs):
    content = json.loads((Path(settings.BASE_DIR) / path).read_text())
    approve_package(import_package(content, is_official=True, **kwargs))


def test_cra_journey(page, live_server, world):
    page_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    _approve("packages/common/1.1.0.json", kind=PackageKind.QUESTION_SET)
    _approve("packages/eu-cra/1.0.0.json")

    product = Product.objects.create(
        product_family=world["family"], name="Gateway", slug="gateway"
    )
    variant = HardwareVariant.objects.create(product=product, name="Global", slug="global")
    variant.target_markets.set(TargetMarket.objects.filter(code__in=["EU", "US"]))
    revision = HardwareRevision.objects.create(hardware_variant=variant, label="A")
    release = SoftwareRelease.objects.create(product=product, name="Firmware", version="2.0")
    configuration = Configuration.objects.create(
        name="Gateway EU 2.0", hardware_revision=revision, software_release=release
    )

    sign_in(page, live_server, "edna", world["password"])

    # --- Markets on the software release ---------------------------------------------
    page.goto(f"{live_server.url}{reverse('products:product_detail', args=[product.pk])}")
    open_tab(page, "Software releases")
    release_row = page.locator("tr", has_text="Firmware 2.0").first
    expect(release_row).to_contain_text("Markets: as hardware variant")
    release_row.get_by_role("button", name="Edit").click()  # needs Alpine
    edit_form = form_for(page, "products:software_release_edit", release.pk)
    edit_form.locator("[name=target_markets]").select_option(label="EU — European Union")
    submit(page, edit_form)
    open_tab(page, "Software releases")
    expect(page.locator("tr", has_text="Firmware 2.0").first).to_contain_text("Markets: EU")
    assert configuration.effective_market_codes() == {"EU"}

    # --- The CRA questionnaire --------------------------------------------------------
    page.goto(
        f"{live_server.url}{reverse('assessments:configuration_detail', args=[configuration.pk])}"
    )
    expect(page.get_by_role("heading", name="Questions")).to_be_visible()
    answer(page, "What kind of product is this?", "hardware_with_software")
    answer(page, "What is your role for this product?", "manufacturer")
    answer(page, "Is the product supplied in the course of a commercial activity?", "Yes")
    answer(page, "Can the product exchange digital data", "Yes")

    date_question = "When was this software release first placed on the market?"
    date_input = page.locator("tr", has_text=date_question).locator("[name=value]")
    expect(date_input).to_have_attribute("type", "date")
    answer(page, date_question, "2028-02-01")
    expect(page.locator("tr", has_text=date_question).locator("td").nth(1)).to_have_text(
        "2028-02-01"
    )

    category_row = page.locator("tr", has_text="Which Annex III or Annex IV category")
    expect(category_row).to_contain_text("Good to understand before you answer")

    # --- Dated requirements on the assessment page -----------------------------------
    with mock.patch("django.utils.timezone.localdate", return_value=date(2026, 10, 1)):
        with page.expect_navigation():
            page.get_by_role("button", name="Start new assessment").click()
        assert re.search(r"/assessments/\d+/$", page.url)
        expect(page.get_by_role("heading", name="eu-cra@2024-2847@2026-10")).to_be_visible()
        expect(page.get_by_text("Economic operator role: manufacturer")).to_be_visible()
        expect(
            page.get_by_text(re.compile(r"art_14_report_exploited_vulnerabilities"))
        ).to_be_visible()
        upcoming = page.locator("p", has_text="Not in force yet:")
        expect(upcoming).to_contain_text("annex_i_2a_no_known_exploitable_vulnerabilities")
        expect(upcoming).to_contain_text("(from 2027-12-11)")

    assert page_errors == []
