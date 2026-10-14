"""Dark mode: native form controls must follow the theme.

A white checkbox on a dark page was reported three times, so this loads the
main pages with the dark theme and inspects every visible form control in the
browser: it must be drawn in the dark colour scheme, and text fields, selects
and textareas must have a dark background. Add a page to ``PAGES`` when a new
screen gets form controls.
"""

import pytest
from django.urls import reverse

from apps.products.models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareRelease,
)

from .test_assessment_journey import sign_in

INSPECT = """
() => [...document.querySelectorAll('input, select, textarea')]
  .filter(el => el.type !== 'hidden' && el.getClientRects().length > 0)
  .map(el => {
    const style = getComputedStyle(el);
    const [r, g, b] = (style.backgroundColor.match(/[\\d.]+/g) || [0, 0, 0]).map(Number);
    return {
      control: `${el.tagName.toLowerCase()}[type=${el.type || 'text'}][name=${el.name}]`,
      scheme: style.colorScheme,
      luminance: (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255,
      field: el.tagName !== 'INPUT'
        || !['checkbox', 'radio', 'submit', 'button'].includes(el.type),
    };
  })
"""


@pytest.fixture
def configuration(world):
    product = Product.objects.create(product_family=world["family"], name="Widget", slug="widget")
    variant = HardwareVariant.objects.create(product=product, name="EU", slug="eu")
    revision = HardwareRevision.objects.create(hardware_variant=variant, label="A")
    release = SoftwareRelease.objects.create(product=product, name="Firmware", version="1.0")
    return Configuration.objects.create(
        name="Widget EU 1.0", hardware_revision=revision, software_release=release
    )


def pages(configuration):
    product = configuration.product
    return {
        "report form (checkboxes)": reverse("reports:generate", args=[configuration.pk]),
        "product page": reverse("products:product_detail", args=[product.pk]),
        "questionnaire": reverse("assessments:configuration_detail", args=[configuration.pk]),
        "risk register": reverse("risk:register", args=[configuration.pk]),
        "evidence list": reverse("evidence:product_list", args=[product.pk]),
        "compare": reverse("core:compare"),
    }


def assert_dark_controls(page, where):
    page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
    controls = page.evaluate(INSPECT)
    wrong = [
        f"{c['control']} (color-scheme {c['scheme']}, background luminance {c['luminance']:.2f})"
        for c in controls
        if c["scheme"] != "dark" or (c["field"] and c["luminance"] > 0.4)
    ]
    assert not wrong, f"{where}: form controls not drawn dark: {wrong}"
    return len(controls)


def test_form_controls_are_dark_in_dark_mode(page, live_server, world, configuration):
    page.goto(f"{live_server.url}{reverse('login')}")
    assert_dark_controls(page, "login")

    sign_in(page, live_server, "edna", world["password"])
    inspected = 0
    for where, url in pages(configuration).items():
        page.goto(f"{live_server.url}{url}")
        inspected += assert_dark_controls(page, where)
    # The report form alone has checkboxes and a title field: a page that
    # renders no controls would let the guard pass without checking anything.
    assert inspected >= 10
