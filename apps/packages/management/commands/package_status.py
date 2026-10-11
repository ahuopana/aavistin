from django.core.management.base import BaseCommand

from apps.packages.models import PackageKind, RequirementPackage


class Command(BaseCommand):
    help = "List imported packages with kind, version and status (draft, approved, ...)."

    def add_arguments(self, parser):
        parser.add_argument("source", nargs="?", help="Only show this package source.")
        parser.add_argument("--kind", choices=PackageKind.values, help="Only show this kind.")

    def handle(self, source, kind, **options):
        packages = RequirementPackage.objects.order_by("source", "imported_at", "pk")
        if source:
            packages = packages.filter(source=source)
        if kind:
            packages = packages.filter(kind=kind)

        rows = [(p.source, p.version, p.kind, p.status, str(len(p.lint_errors))) for p in packages]
        if not rows:
            self.stdout.write("No packages imported.")
            return
        header = ("SOURCE", "VERSION", "KIND", "STATUS", "LINT ERRORS")
        widths = [max(len(r[i]) for r in [header, *rows]) for i in range(len(header))]
        for row in [header, *rows]:
            cells = (c.ljust(w) for c, w in zip(row, widths, strict=True))
            self.stdout.write("  ".join(cells).rstrip())
