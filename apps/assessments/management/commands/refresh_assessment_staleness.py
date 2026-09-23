from django.core.management.base import BaseCommand

from apps.assessments.models import Assessment, AssessmentStatus
from apps.assessments.services import recompute_staleness


class Command(BaseCommand):
    help = "Recompute Assessment.stale for every approved assessment."

    def handle(self, **options):
        newly_stale = 0
        checked = 0
        for assessment in Assessment.objects.filter(status=AssessmentStatus.APPROVED):
            checked += 1
            if recompute_staleness(assessment):
                newly_stale += 1
        self.stdout.write(
            self.style.SUCCESS(f"Checked {checked} approved assessment(s); {newly_stale} stale.")
        )
