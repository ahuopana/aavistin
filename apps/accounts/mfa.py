"""Two-factor authentication policy (docs/adr/0045-two-factor-authentication.md).

TOTP via django-otp (works with Microsoft Authenticator, Google Authenticator and
any RFC 6238 app) plus single-use recovery codes. Required for administrators
(``is_staff`` / ``is_superuser``) and for every local account; directory (LDAP) and
SSO users are expected to be protected at their identity provider.
"""

import base64
import io
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core import throttle

from .models import AuthSource

MFA_SCOPE = "mfa-user"
RECOVERY_DEVICE_NAME = "recovery"
RECOVERY_CODE_COUNT = 10


def requires_mfa(user) -> bool:
    if not settings.MFA_ENFORCE or not user.is_authenticated:
        return False
    return bool(user.is_staff or user.is_superuser or user.auth_source == AuthSource.LOCAL)


def has_confirmed_device(user) -> bool:
    return TOTPDevice.objects.filter(user=user, confirmed=True).exists()


def locked_for(user) -> int:
    """Seconds left on this user's second-factor lock; 0 when verification is allowed."""
    return throttle.retry_after(
        MFA_SCOPE,
        str(user.pk),
        limit=settings.LOGIN_THROTTLE_MAX_FAILURES,
        window=settings.LOGIN_THROTTLE_WINDOW_SECONDS,
    )


def record_failure(user) -> None:
    throttle.record(MFA_SCOPE, str(user.pk))


def safe_next(request, default: str = "/") -> str:
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


def qr_svg(uri: str) -> str:
    """The provisioning URI as an inline SVG QR code. We generate the markup from
    our own URI, so it is safe to mark as such."""
    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer)
    return mark_safe(buffer.getvalue().decode())  # noqa: S308


def provisioning_uri(device) -> str:
    """The otpauth:// URI authenticator apps scan. Defaults (SHA-1, 6 digits, 30 s) are
    the ones every app supports."""
    issuer = settings.OTP_TOTP_ISSUER
    account = quote(f"{issuer}:{device.user.get_username()}")
    return (
        f"otpauth://totp/{account}?secret={manual_secret(device)}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={device.digits}&period={device.step}"
    )


def manual_secret(device) -> str:
    return base64.b32encode(device.bin_key).decode().rstrip("=")


def issue_recovery_codes(user) -> list[str]:
    """Replace the user's recovery codes with a fresh set and return them (shown once)."""
    StaticDevice.objects.filter(user=user, name=RECOVERY_DEVICE_NAME).delete()
    device = StaticDevice.objects.create(user=user, name=RECOVERY_DEVICE_NAME, confirmed=True)
    codes = [StaticToken.random_token() for _ in range(RECOVERY_CODE_COUNT)]
    StaticToken.objects.bulk_create([StaticToken(device=device, token=c) for c in codes])
    return codes


class MFAEnforcementMiddleware:
    """Send signed-in users who need a second factor, and have not given it this
    session, to enrolment (no device yet) or verification (device enrolled). Must sit
    after ``OTPMiddleware``."""

    def __init__(self, get_response):
        self.get_response = get_response

    def _exempt_paths(self):
        return {
            reverse("accounts:mfa_setup"),
            reverse("accounts:mfa_verify"),
            reverse("logout"),
            reverse("login"),
        }

    def __call__(self, request):
        user = request.user
        if (
            requires_mfa(user)
            and not user.is_verified()
            and request.path not in self._exempt_paths()
        ):
            name = "accounts:mfa_verify" if has_confirmed_device(user) else "accounts:mfa_setup"
            target = reverse(name)
            if request.method == "GET":
                target += "?next=" + quote(request.get_full_path(), safe="")
            if request.headers.get("HX-Request"):
                response = HttpResponse(status=204)
                response["HX-Redirect"] = target
                return response
            return redirect(target)
        return self.get_response(request)
