from django.core.management.base import BaseCommand

from apps.risk.approval import recompute_all_staleness


class Command(BaseCommand):
    help = "Recompute RiskAssessment.stale for every approved risk assessment."

    def handle(self, **options):
        checked, newly_stale = recompute_all_staleness()
        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {checked} approved risk assessment(s); {newly_stale} stale."
            )
        )
