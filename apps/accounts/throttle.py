"""Failed-login throttling (docs/adr/0044).

Enforced in an authentication backend, so the sign-in page, the admin login and
anything else that calls ``authenticate`` are all covered, whichever backend would
have checked the password. Locks are per normalised username (whether or not it
exists, so a lock reveals nothing about accounts) and per client address.
"""

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.exceptions import PermissionDenied
from django.dispatch import receiver

from apps.core import throttle

USER_SCOPE = "login-user"
IP_SCOPE = "login-ip"


def _username_key(credentials: dict) -> str:
    return str(credentials.get("username") or "").strip().lower()[:150]


def lockout_seconds(request, username: str) -> int:
    """Seconds the caller must wait before a login attempt is considered; 0 if allowed."""
    if not settings.LOGIN_THROTTLE_ENABLED:
        return 0
    window = settings.LOGIN_THROTTLE_WINDOW_SECONDS
    waits = []
    if request is not None:
        waits.append(
            throttle.retry_after(
                IP_SCOPE,
                throttle.client_ip(request),
                limit=settings.LOGIN_THROTTLE_MAX_FAILURES_PER_IP,
                window=window,
            )
        )
    if username:
        waits.append(
            throttle.retry_after(
                USER_SCOPE,
                username.strip().lower()[:150],
                limit=settings.LOGIN_THROTTLE_MAX_FAILURES,
                window=window,
            )
        )
    return max(waits, default=0)


class ThrottleBackend:
    """Listed first in AUTHENTICATION_BACKENDS: while locked, raising PermissionDenied
    makes ``authenticate`` stop before any other backend sees the password."""

    def authenticate(self, request, username=None, **kwargs):
        if lockout_seconds(request, username or ""):
            raise PermissionDenied("Too many failed sign-in attempts.")
        return None

    def get_user(self, user_id):
        # Never authenticates anyone itself, but test clients' force_login() and other
        # code that picks the first configured backend still need to load users.
        return ModelBackend().get_user(user_id)


@receiver(user_login_failed, dispatch_uid="accounts.record_login_failure")
def record_failure(sender, credentials, request=None, **kwargs):
    if request is None or not settings.LOGIN_THROTTLE_ENABLED:
        return
    username = _username_key(credentials)
    if lockout_seconds(request, username):
        return  # already locked: don't extend the lock with attempts that were refused
    throttle.record(IP_SCOPE, throttle.client_ip(request))
    if username:
        throttle.record(USER_SCOPE, username)


@receiver(user_logged_in, dispatch_uid="accounts.clear_login_failures")
def clear_failures(sender, request, user, **kwargs):
    if settings.LOGIN_THROTTLE_ENABLED:
        throttle.clear(USER_SCOPE, user.get_username().strip().lower()[:150])
