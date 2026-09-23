import json

from django.core.management.base import BaseCommand, CommandError

from apps.packages.importer import PackageImportError, import_package
from apps.packages.models import PackageKind


class Command(BaseCommand):
    help = (
        "Import a requirement/method/catalog package JSON file "
        "(validate, lint, run fixtures; does not approve)."
    )

    def add_arguments(self, parser):
        parser.add_argument("path", help="Path to a package .json file")
        parser.add_argument(
            "--kind",
            choices=PackageKind.values,
            default=PackageKind.REQUIREMENT,
            help="Package kind (default: requirement).",
        )
        parser.add_argument(
            "--official",
            action="store_true",
            help="Mark as an official, maintainer-reviewed package.",
        )

    def handle(self, path, kind, official, **options):
        with open(path) as f:
            content = json.load(f)

        try:
            package = import_package(content, kind=kind, is_official=official)
        except PackageImportError as exc:
            raise CommandError(f"schema validation failed: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(f"Imported {package.source}@{package.version} — {package.status}")
        )
        for issue in package.lint_report:
            style = self.style.ERROR if issue["severity"] == "error" else self.style.WARNING
            self.stdout.write(
                style(f"  [{issue['severity']}] {issue['path']}: {issue['message']}")
            )
        for result in package.fixture_report:
            mark = "PASS" if result["passed"] else "FAIL"
            self.stdout.write(f"  fixture {result['id']}: {mark}")
            for error in result["errors"]:
                self.stdout.write(self.style.ERROR(f"    {error}"))
