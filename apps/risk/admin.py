from django.contrib import admin, messages
from simple_history.admin import SimpleHistoryAdmin

from .approval import RiskAssessmentError, approve_risk_assessment
from .models import (
    AssetRating,
    Control,
    HazardCause,
    Rating,
    RiskAssessment,
    RiskEntry,
    ThreatConsequence,
    Treatment,
)


class AssetRatingInline(admin.TabularInline):
    model = AssetRating
    extra = 0


class ConsequenceInline(admin.TabularInline):
    model = ThreatConsequence
    fk_name = "threat"
    extra = 0


class RatingInline(admin.TabularInline):
    model = Rating
    extra = 0


class HazardCauseInline(admin.TabularInline):
    model = HazardCause
    fk_name = "hazard"
    extra = 0


@admin.register(RiskEntry)
class RiskEntryAdmin(SimpleHistoryAdmin):
    list_display = ("label", "entry_type", "product", "suggestion_status", "is_baseline")
    list_filter = ("entry_type", "suggestion_status", "product")
    inlines = [AssetRatingInline, ConsequenceInline, RatingInline, HazardCauseInline]


@admin.register(Control)
class ControlAdmin(SimpleHistoryAdmin):
    list_display = ("name", "product", "status")
    list_filter = ("status", "product")
    filter_horizontal = ("threats", "hazard_causes")


@admin.register(Treatment)
class TreatmentAdmin(SimpleHistoryAdmin):
    list_display = (
        "entry",
        "method",
        "treatment_type",
        "residual_severity",
        "residual_likelihood",
    )
    list_filter = ("treatment_type",)


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(SimpleHistoryAdmin):
    list_display = ("id", "configuration", "status", "stale", "created_at")
    list_filter = ("status", "stale")
    readonly_fields = ("snapshot", "approved_at", "approved_by")
    actions = ["approve_selected"]

    @admin.action(description="Approve selected risk assessments (freezes a snapshot)")
    def approve_selected(self, request, queryset):
        approved = 0
        for risk_assessment in queryset:
            try:
                approve_risk_assessment(risk_assessment, actor=request.user)
                approved += 1
            except RiskAssessmentError as exc:
                self.message_user(request, f"{risk_assessment}: {exc}", level=messages.ERROR)
        if approved:
            self.message_user(
                request, f"Approved {approved} risk assessment(s).", level=messages.SUCCESS
            )
