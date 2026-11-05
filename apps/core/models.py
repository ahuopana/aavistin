from django.db import models


class ThrottleEvent(models.Model):
    """One countable event (a failed login, a verify request) for rate limiting.

    Kept in PostgreSQL rather than a cache so limits hold across gunicorn
    workers and restarts without adding a Redis dependency (ADR 0049). Rows
    are pruned on write by ``apps.core.throttle.record``.
    """

    scope = models.CharField(max_length=32)
    key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["scope", "key", "created_at"])]

    def __str__(self):
        return f"{self.scope}:{self.key} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
