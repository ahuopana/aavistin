"""Sliding-window rate limiting backed by the database (docs/adr/0044)."""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import ThrottleEvent

RETENTION = timedelta(hours=24)


def client_ip(request) -> str:
    """The caller's address. ``REMOTE_ADDR`` unless ``CLIENT_IP_HEADER`` names a header
    set by a trusted reverse proxy (e.g. ``HTTP_X_FORWARDED_FOR``); the last entry is
    used, since that is the one the proxy itself appended."""
    header = getattr(settings, "CLIENT_IP_HEADER", "")
    if header:
        value = request.META.get(header, "")
        if value:
            return value.split(",")[-1].strip()[:64]
    return request.META.get("REMOTE_ADDR", "")[:64] or "unknown"


def record(scope: str, key: str) -> None:
    ThrottleEvent.objects.create(scope=scope, key=key[:255])
    ThrottleEvent.objects.filter(created_at__lt=timezone.now() - RETENTION).delete()


def clear(scope: str, key: str) -> None:
    ThrottleEvent.objects.filter(scope=scope, key=key[:255]).delete()


def retry_after(scope: str, key: str, *, limit: int, window: int) -> int:
    """Seconds until another event is allowed; 0 when under ``limit`` within ``window``."""
    now = timezone.now()
    recent = list(
        ThrottleEvent.objects.filter(
            scope=scope, key=key[:255], created_at__gte=now - timedelta(seconds=window)
        )
        .order_by("-created_at")
        .values_list("created_at", flat=True)[:limit]
    )
    if len(recent) < limit:
        return 0
    # Blocked until the oldest of the ``limit`` newest events leaves the window.
    return max(1, int((recent[-1] + timedelta(seconds=window) - now).total_seconds()) + 1)
