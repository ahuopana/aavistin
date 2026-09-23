from django.core.management.base import BaseCommand, CommandError

from apps.packages.importer import PackageImportError, approve_package
from apps.packages.models import RequirementPackage


class Command(BaseCommand):
    help = "Approve (publish) an imported package version."

    def add_arguments(self, parser):
        parser.add_argument("source")
        parser.add_argument("version")

    def handle(self, source, version, **options):
        try:
            package = RequirementPackage.objects.get(source=source, version=version)
        except RequirementPackage.DoesNotExist as exc:
            raise CommandError(f"no such package: {source}@{version}") from exc

        try:
            approve_package(package)
        except PackageImportError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Approved {package.source}@{package.version}"))
