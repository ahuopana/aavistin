from django.core.management.base import BaseCommand

from apps.assessments.services import recompute_all_staleness


class Command(BaseCommand):
    help = "Recompute Assessment.stale for every approved assessment."

    def handle(self, **options):
        checked, newly_stale = recompute_all_staleness()
        self.stdout.write(
            self.style.SUCCESS(f"Checked {checked} approved assessment(s); {newly_stale} stale.")
        )
