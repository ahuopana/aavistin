"""Enqueues periodic tasks on a fixed interval.

django-tasks (see docs/adr/0007-background-job-backend.md) has no
built-in cron-style scheduling — this fills that gap with the smallest
thing that works: a loop that sleeps and enqueues. It only enqueues; the
`worker` service (running `manage.py db_worker`) does the actual work.
Runs as its own container/process (docker-compose's `scheduler` service),
separate from `worker`, so a slow task never delays the next tick.
"""

import signal
import time

from django.core.management.base import BaseCommand

from apps.assessments.tasks import refresh_staleness_task as refresh_assessment_staleness
from apps.risk.tasks import refresh_staleness_task as refresh_risk_staleness

# (task, how often to enqueue it, in seconds)
SCHEDULE = [
    (refresh_assessment_staleness, 3600),
    (refresh_risk_staleness, 3600),
]


class Command(BaseCommand):
    help = "Enqueue periodic background tasks on a fixed interval (no cron)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--tick",
            type=int,
            default=60,
            help="Seconds between checks for due tasks (default: 60).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            help="Enqueue every scheduled task once and exit, instead of looping.",
        )

    def handle(self, tick, once, **options):
        running = True

        def stop(signum, frame):
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

        if once:
            for task, _interval in SCHEDULE:
                task.enqueue()
                self.stdout.write(f"Enqueued {task}")
            return

        last_run = dict.fromkeys(range(len(SCHEDULE)), 0.0)
        self.stdout.write(self.style.SUCCESS(f"Scheduler started (tick={tick}s)."))
        while running:
            now = time.monotonic()
            for i, (task, interval) in enumerate(SCHEDULE):
                if now - last_run[i] >= interval:
                    task.enqueue()
                    last_run[i] = now
                    self.stdout.write(f"Enqueued {task}")
            time.sleep(tick)
