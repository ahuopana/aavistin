from django.contrib import admin, messages

from .importer import PackageImportError, approve_package
from .models import RequirementPackage


@admin.register(RequirementPackage)
class RequirementPackageAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "version",
        "package_type",
        "jurisdiction",
        "status",
        "is_official",
        "imported_at",
    )
    list_filter = ("status", "package_type", "is_official", "jurisdiction")
    readonly_fields = (
        "content",
        "lint_report",
        "fixture_report",
        "diff_from_previous",
        "imported_at",
        "imported_by",
        "approved_at",
        "approved_by",
    )
    actions = ["approve_selected"]

    @admin.action(description="Approve selected packages (publishes; supersedes prior version)")
    def approve_selected(self, request, queryset):
        approved = 0
        for package in queryset:
            try:
                approve_package(package, actor=request.user)
                approved += 1
            except PackageImportError as exc:
                self.message_user(request, f"{package}: {exc}", level=messages.ERROR)
        if approved:
            self.message_user(request, f"Approved {approved} package(s).", level=messages.SUCCESS)
