"""Fixtures for the browser (end-to-end) tests.

These drive a real Chromium against ``live_server``. They are marked
``e2e`` and excluded from the default ``pytest`` run (see ``pyproject.toml``);
run them with ``uv run pytest -m e2e`` after ``uv run playwright install chromium``.
"""

import json
import os
from pathlib import Path

import pytest
from django.conf import settings

from apps.accounts.models import User
from apps.orgs.models import Organisation, ProductFamily, Role, RoleAssignment
from apps.packages.importer import approve_package, import_package
from apps.products.models import TargetMarket

# Playwright's sync API runs an event loop in the test thread, which makes
# Django refuse ORM calls there. The tests only touch the ORM to seed data
# and to trigger background jobs, so this is safe.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

PASSWORD = "e2e-pass-123"
MARKETS = [
    ("EU", "European Union"),
    ("UK", "United Kingdom"),
    ("US", "United States"),
    ("CA", "Canada"),
]


def pytest_collection_modifyitems(items):
    for item in items:
        if Path(str(item.fspath)).parent.name == "e2e":
            item.add_marker(pytest.mark.e2e)


def _ensure_target_markets():
    for code, name in MARKETS:
        TargetMarket.objects.get_or_create(code=code, defaults={"name": name})


@pytest.fixture(scope="session", autouse=True)
def _restore_reference_data(django_db_blocker):
    """Live-server tests flush the database on teardown, which also wipes the
    target markets seeded by a migration. Put them back at the end of the
    session so a reused test database stays valid for the unit tests."""
    yield
    with django_db_blocker.unblock():
        _ensure_target_markets()


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Allow pointing at a pre-installed Chromium (e.g. in a sandbox)."""
    executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
    if executable:
        return {**browser_type_launch_args, "executable_path": executable}
    return browser_type_launch_args


@pytest.fixture
def block_external_requests(page, live_server):
    """Keep the tests hermetic: only the live server may be contacted (Google
    Fonts and the like are aborted, so the system fallback font is used)."""
    page.route(
        lambda url: not url.startswith(live_server.url),
        lambda route: route.abort(),
    )


@pytest.fixture
def world(transactional_db, block_external_requests):
    """An organisation with an editor, an approver and an approved demo package."""
    _ensure_target_markets()
    org = Organisation.objects.create(name="Acme", slug="acme")
    family = ProductFamily.objects.create(organisation=org, name="Sensors", slug="sensors")

    editor = User.objects.create_user(username="edna", password=PASSWORD)
    approver = User.objects.create_user(username="ana", password=PASSWORD)
    RoleAssignment.objects.create(role=Role.EDITOR, user=editor, product_family=family)
    RoleAssignment.objects.create(role=Role.VIEWER, user=editor, product_family=family)
    RoleAssignment.objects.create(role=Role.APPROVER, user=approver, product_family=family)
    RoleAssignment.objects.create(role=Role.VIEWER, user=approver, product_family=family)

    package_file = Path(settings.BASE_DIR) / "packages" / "demo-widget-safety" / "1.0.0.json"
    package = import_package(json.loads(package_file.read_text()), is_official=True)
    approve_package(package)

    return {"family": family, "editor": editor, "approver": approver, "password": PASSWORD}
