from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Evidence, EvidenceFile, EvidenceLink


class EvidenceLinkInline(admin.TabularInline):
    model = EvidenceLink
    extra = 0


@admin.register(EvidenceFile)
class EvidenceFileAdmin(admin.ModelAdmin):
    list_display = ("checksum", "content_type", "size", "uploaded_at", "uploaded_by")
    readonly_fields = ("checksum", "size", "uploaded_at")


@admin.register(Evidence)
class EvidenceAdmin(SimpleHistoryAdmin):
    list_display = ("title", "product", "kind", "last_audit_date", "valid_until")
    list_filter = ("kind", "product")
    inlines = [EvidenceLinkInline]


@admin.register(EvidenceLink)
class EvidenceLinkAdmin(admin.ModelAdmin):
    list_display = ("evidence", "target_type", "control", "requirement_id")
    list_filter = ("target_type",)
