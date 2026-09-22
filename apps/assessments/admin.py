from django.contrib import admin, messages

from .models import Answer, Assessment
from .services import AssessmentError, approve_assessment


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("question_id", "owner", "value", "needs_confirmation", "updated_at")
    list_filter = ("needs_confirmation",)
    search_fields = ("question_id",)


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ("id", "configuration", "status", "stale", "sod_warning", "created_at")
    list_filter = ("status", "stale")
    readonly_fields = ("snapshot", "approved_at", "approved_by", "stale", "sod_warning")
    actions = ["approve_selected"]

    @admin.action(description="Approve selected assessments (freezes a snapshot)")
    def approve_selected(self, request, queryset):
        approved = 0
        for assessment in queryset:
            try:
                approve_assessment(assessment, actor=request.user)
                approved += 1
            except AssessmentError as exc:
                self.message_user(request, f"{assessment}: {exc}", level=messages.ERROR)
        if approved:
            self.message_user(
                request, f"Approved {approved} assessment(s).", level=messages.SUCCESS
            )
