import json

from django import forms
from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse

from .importer import PackageImportError, approve_package, import_package
from .models import PackageKind, PackageStatus, RequirementPackage


class ImportPackageForm(forms.Form):
    file = forms.FileField(label="Package JSON file")
    kind = forms.ChoiceField(choices=PackageKind.choices, initial=PackageKind.REQUIREMENT)
    is_official = forms.BooleanField(
        required=False, label="Official (maintainer-reviewed, lives in version control)"
    )
    force = forms.BooleanField(
        required=False, label="Import even if question sets it uses are not yet approved"
    )


@admin.register(RequirementPackage)
class RequirementPackageAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "version",
        "kind",
        "package_type",
        "jurisdiction",
        "status",
        "is_official",
        "imported_at",
    )
    list_filter = ("source", "kind", "status", "package_type", "is_official", "jurisdiction")
    search_fields = ("source", "version", "title")
    # All versions of one package sit together, newest first.
    ordering = ("source", "-imported_at")
    actions = ["approve_selected"]

    def get_readonly_fields(self, request, obj=None):
        # Status changes only through import and approval, never by editing.
        return [f.name for f in self.model._meta.fields if f.editable]

    def has_add_permission(self, request):
        # Packages are created through the import page, not the add form.
        return False

    def get_urls(self):
        custom = path(
            "import/",
            self.admin_site.admin_view(self.import_view),
            name="packages_requirementpackage_import",
        )
        return [custom, *super().get_urls()]

    def import_view(self, request):
        if not super().has_add_permission(request):
            return redirect("admin:index")
        form = ImportPackageForm(request.POST or None, request.FILES or None)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                content = json.load(data["file"])
                package = import_package(
                    content,
                    kind=data["kind"],
                    is_official=data["is_official"],
                    actor=request.user,
                    force=data["force"],
                )
            except (ValueError, UnicodeDecodeError):
                form.add_error("file", "Not a valid JSON file.")
            except PackageImportError as exc:
                form.add_error(None, str(exc))
            else:
                level = messages.SUCCESS if not package.lint_errors else messages.WARNING
                self.message_user(
                    request,
                    f"Imported {package.source}@{package.version} as {package.status} "
                    f"({len(package.lint_errors)} lint errors).",
                    level=level,
                )
                return redirect(
                    reverse("admin:packages_requirementpackage_change", args=[package.pk])
                )
        context = {**self.admin_site.each_context(request), "title": "Import package", "form": form}
        return TemplateResponse(
            request, "admin/packages/requirementpackage/import.html", context
        )

    def get_actions(self, request):
        # Bulk delete doesn't check per-object permission, so it is removed.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def has_delete_permission(self, request, obj=None):
        # Published versions are never removed; only unpublished drafts can be.
        if obj is not None and obj.status in (PackageStatus.APPROVED, PackageStatus.SUPERSEDED):
            return False
        return super().has_delete_permission(request, obj)

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
