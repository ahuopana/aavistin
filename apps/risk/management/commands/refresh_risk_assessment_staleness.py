from django.core.management.base import BaseCommand

from apps.risk.approval import recompute_staleness
from apps.risk.models import RiskAssessment, RiskAssessmentStatus


class Command(BaseCommand):
    help = "Recompute RiskAssessment.stale for every approved risk assessment."

    def handle(self, **options):
        newly_stale = 0
        checked = 0
        for risk_assessment in RiskAssessment.objects.filter(status=RiskAssessmentStatus.APPROVED):
            checked += 1
            if recompute_staleness(risk_assessment):
                newly_stale += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {checked} approved risk assessment(s); {newly_stale} stale."
            )
        )
