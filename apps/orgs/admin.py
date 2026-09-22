from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Organisation, ProductFamily, RoleAssignment


@admin.register(Organisation)
class OrganisationAdmin(SimpleHistoryAdmin):
    list_display = ("name", "slug", "sod_policy")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ProductFamily)
class ProductFamilyAdmin(SimpleHistoryAdmin):
    list_display = ("name", "organisation", "sod_policy_override")
    list_filter = ("organisation",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(SimpleHistoryAdmin):
    list_display = ("__str__", "role", "organisation", "product_family", "created_at")
    list_filter = ("role",)
