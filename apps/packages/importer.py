"""Import pipeline: schema validation -> semantic lint -> fixtures -> diff -> save.

Approval is a separate, explicit step (see approve_package below) — never
automatic, per docs/architecture.md: "Every import shows a diff against
the previous version and requires approval before publishing."
"""

import json
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from jsonschema import Draft202012Validator

from .diffing import diff_packages
from .fixtures_runner import run_fixtures
from .linting import lint_package
from .models import PackageStatus, RequirementPackage

SCHEMA_PATH = Path(settings.BASE_DIR) / "schemas" / "package.schema.json"


class PackageImportError(Exception):
    """Raised when a package fails structural (JSON Schema) validation,
    or when an operation's preconditions (e.g. approval status) aren't met."""


def _load_schema() -> dict:
    with SCHEMA_PATH.open() as f:
        return json.load(f)


def validate_schema(content: dict) -> None:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(content), key=lambda e: str(list(e.absolute_path)))
    if errors:
        messages = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        ]
        raise PackageImportError("; ".join(messages))


def import_package(content: dict, *, is_official: bool = False, actor=None) -> RequirementPackage:
    """Validate, lint, run fixtures and save a new package version.

    Raises PackageImportError on structural (schema) failure — the
    package is not saved at all in that case. Semantic lint and fixture
    failures do *not* raise: the package is saved with the failures
    recorded on it (status stays below 'fixtures_passed'), so a curator
    can review and fix the content. Importing never implies approval.
    """
    validate_schema(content)

    existing = RequirementPackage.objects.filter(source=content["source"])
    lint_report = lint_package(content, is_official=is_official, existing_packages=existing)

    status = PackageStatus.DRAFT
    fixture_report = []
    if not any(issue["severity"] == "error" for issue in lint_report):
        status = PackageStatus.LINTED
        fixture_report = run_fixtures(content)
        if fixture_report and all(r["passed"] for r in fixture_report):
            status = PackageStatus.FIXTURES_PASSED

    previous = (
        existing.filter(status__in=[PackageStatus.APPROVED, PackageStatus.SUPERSEDED])
        .order_by("-imported_at")
        .first()
    )
    diff = diff_packages(previous.content, content) if previous else None

    return RequirementPackage.objects.create(
        source=content["source"],
        version=content["version"],
        package_type=content["type"],
        jurisdiction=content["jurisdiction"],
        title=content.get("title", ""),
        content=content,
        is_official=is_official,
        redistributable=content.get("redistributable", True),
        status=status,
        lint_report=lint_report,
        fixture_report=fixture_report,
        diff_from_previous=diff,
        supersedes_package=previous,
        imported_by=actor,
    )


def approve_package(package: RequirementPackage, *, actor=None) -> RequirementPackage:
    """Publish a package version. Requires clean lint and passing fixtures."""
    if package.status != PackageStatus.FIXTURES_PASSED:
        raise PackageImportError(
            f"cannot approve a package in status '{package.status}'; "
            "it must have status 'fixtures_passed' (clean lint, all fixtures passing, "
            "and at least one fixture)"
        )

    RequirementPackage.objects.filter(
        source=package.source, status=PackageStatus.APPROVED
    ).exclude(pk=package.pk).update(status=PackageStatus.SUPERSEDED)

    package.status = PackageStatus.APPROVED
    package.approved_at = timezone.now()
    package.approved_by = actor
    package.save(update_fields=["status", "approved_at", "approved_by"])
    return package
