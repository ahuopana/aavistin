"""End-to-end journey: from an empty portfolio to an approved, then stale, assessment.

One editor builds the product and answers the questions, a different user
(the approver, so separation of duties is respected) approves the assessment,
and a later answer change makes the approved snapshot go stale. Everything
goes through the real UI in a real browser; the ORM is only used to seed users
and the requirement package, look up ids, and run the staleness job (which the
app runs on a schedule).
"""

import re

from django.core.management import call_command
from django.urls import reverse
from playwright.sync_api import expect

from apps.products.models import HardwareRevision, HardwareVariant

POWER_QUESTION = "Does the widget have a power source?"
TOY_QUESTION = "Is the widget marketed as a toy?"
RATED_POWER_QUESTION = "Rated power"
HIGH_POWER_FINDING = "Rated power exceeds 100W"


def sign_in(page, live_server, username, password):
    page.goto(f"{live_server.url}{reverse('login')}")
    page.fill("#id_username", username)
    page.fill("#id_password", password)
    with page.expect_navigation():
        page.get_by_role("button", name="Sign in").click()
    expect(page.locator(".app-user")).to_have_text(username)


def sign_out(page):
    with page.expect_navigation():
        page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_role("link", name="Sign in")).to_be_visible()


def submit(page, form):
    """Submit ``form`` by clicking its first submit button and wait for the redirect."""
    with page.expect_navigation():
        form.locator("button[type=submit]").first.click()


def form_for(page, url_name, *args):
    return page.locator(f'form[action="{reverse(url_name, args=args)}"]')


def open_tab(page, name):
    """Switch the product page to a tab (each form submit returns to the default tab)."""
    page.get_by_role("tab", name=re.compile(name)).click()


def answer(page, question, value):
    """Set the answer to ``question`` through its row's form."""
    row = page.locator("tr", has_text=question)
    control = row.locator("[name=value]")
    if control.evaluate("el => el.tagName") == "SELECT":
        control.select_option(label=value)
    else:
        control.fill(value)
    with page.expect_navigation():
        row.get_by_role("button", name="Save").click()


def test_assessment_journey(page, live_server, world):
    page_errors = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    password = world["password"]

    # --- The editor builds a product -------------------------------------------------
    sign_in(page, live_server, "edna", password)
    page.get_by_role("link", name="Portfolio").click()
    expect(page.get_by_role("heading", name="Portfolio")).to_be_visible()

    submit_form = form_for(page, "products:product_create", world["family"].pk)
    submit_form.locator("[name=name]").fill("TempSense")
    submit_form.locator("[name=slug]").fill("tempsense")
    submit(page, submit_form)

    expect(page.get_by_role("heading", level=1)).to_contain_text("TempSense")
    product_id = int(re.search(r"/products/(\d+)/", page.url).group(1))

    # Hardware variant, then mark it for the EU market via its edit form.
    form = form_for(page, "products:hardware_variant_create", product_id)
    form.locator("[name=name]").fill("EU variant")
    form.locator("[name=slug]").fill("eu-variant")
    submit(page, form)
    variant = HardwareVariant.objects.get(product_id=product_id, slug="eu-variant")

    variant_row = page.locator("tr", has_text="EU variant").first
    variant_row.get_by_role("button", name="Edit").click()  # needs Alpine
    edit_form = form_for(page, "products:hardware_variant_edit", variant.pk)
    edit_form.locator("[name=target_markets]").select_option(label="EU — European Union")
    submit(page, edit_form)
    expect(page.locator("tr", has_text="EU variant").first).to_contain_text("EU")

    # Revision, software release.
    form = form_for(page, "products:hardware_revision_create", variant.pk)
    form.locator("[name=label]").fill("A")
    submit(page, form)
    expect(page.locator("tr:visible", has_text="Rev A")).to_have_count(1)
    revision = HardwareRevision.objects.get(hardware_variant=variant, label="A")

    open_tab(page, "Software releases")
    form = form_for(page, "products:software_release_create", product_id)
    form.locator("[name=name]").fill("Firmware")
    form.locator("[name=version]").fill("1.0.0")
    submit(page, form)

    # Configuration combining the two.
    open_tab(page, "Configurations")
    page.locator("summary", has_text="Add configuration").click()
    form = form_for(page, "products:configuration_create", product_id)
    form.locator("[name=name]").fill("TempSense EU 1.0")
    form.locator("[name=hardware_revision]").select_option(value=str(revision.pk))
    form.locator("[name=software_release]").select_option(index=1)
    submit(page, form)
    open_tab(page, "Configurations")
    expect(page.get_by_role("link", name="TempSense EU 1.0")).to_be_visible()

    # --- The editor answers the questionnaire ----------------------------------------
    page.get_by_role("link", name="TempSense EU 1.0").click()
    expect(page.get_by_role("heading", name="Questions")).to_be_visible()
    for question in (POWER_QUESTION, TOY_QUESTION, RATED_POWER_QUESTION):
        expect(page.locator("tr", has_text=question).locator("td").nth(2)).to_have_text(
            "unanswered"
        )

    answer(page, POWER_QUESTION, "Yes")
    answer(page, TOY_QUESTION, "No")
    answer(page, RATED_POWER_QUESTION, "150")

    for question, shown in (
        (POWER_QUESTION, r"Yes|True"),
        (TOY_QUESTION, r"No|False"),
        (RATED_POWER_QUESTION, r"150"),
    ):
        cells = page.locator("tr", has_text=question).locator("td")
        expect(cells.nth(1)).to_have_text(re.compile(shown))
        expect(cells.nth(2)).not_to_have_text("unanswered")

    # --- A draft assessment evaluates the answers ------------------------------------
    configuration_url = page.url
    with page.expect_navigation():
        page.get_by_role("button", name="Start new assessment").click()
    assessment_url = page.url
    assert re.search(r"/assessments/\d+/$", assessment_url)
    expect(page.get_by_role("heading", name=re.compile(r"Assessment #\d+"))).to_be_visible()
    expect(page.get_by_role("heading", name="demo-widget-safety@1.0.0")).to_be_visible()
    expect(page.get_by_text("In scope", exact=True)).to_be_visible()
    expect(page.get_by_text("Classifications: high_power")).to_be_visible()
    expect(page.get_by_role("cell", name=HIGH_POWER_FINDING)).to_be_visible()
    sign_out(page)

    # --- A different user approves it ------------------------------------------------
    sign_in(page, live_server, "ana", password)
    page.goto(configuration_url)
    expect(page.get_by_role("heading", name="Questions")).to_be_visible()
    # The approver has no editor role: no answer forms, no way to start assessments.
    expect(page.get_by_role("columnheader", name="Set answer")).to_have_count(0)
    expect(page.get_by_role("button", name="Start new assessment")).to_have_count(0)

    page.goto(assessment_url)
    with page.expect_navigation():
        page.get_by_role("button", name=re.compile("Approve")).click()
    expect(page.get_by_text("Assessment approved.")).to_be_visible()
    expect(page.get_by_text("Approved", exact=False).first).to_be_visible()
    expect(page.get_by_text("stale", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("Approve"))).to_have_count(0)
    sign_out(page)

    # --- Changing an answer makes the approved assessment stale ----------------------
    sign_in(page, live_server, "edna", password)
    page.goto(configuration_url)
    answer(page, RATED_POWER_QUESTION, "20")
    expect(page.locator("tr", has_text=RATED_POWER_QUESTION).locator("td").nth(1)).to_have_text(
        "20"
    )

    call_command("refresh_assessment_staleness")  # the scheduled job

    page.goto(assessment_url)
    expect(page.get_by_text("stale", exact=True)).to_be_visible()
    # The approved snapshot is frozen: it still shows the finding from 150 W.
    expect(page.get_by_role("cell", name=HIGH_POWER_FINDING)).to_be_visible()

    assert page_errors == []
