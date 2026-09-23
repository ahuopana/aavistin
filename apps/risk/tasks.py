"""Background tasks for apps.risk.

See docs/adr/0007-background-job-backend.md. Thin wrappers only — all
logic lives in approval.py, called the same way by the manual
`refresh_risk_assessment_staleness` management command.
"""

from django_tasks import task

from .approval import recompute_all_staleness


@task
def refresh_staleness_task() -> None:
    recompute_all_staleness()
