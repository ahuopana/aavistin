from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django_otp import login as otp_login
from django_otp import match_token
from django_otp.plugins.otp_totp.models import TOTPDevice

from . import mfa

SETUP_SESSION_KEY = "mfa_setup_device_id"


@login_required
def mfa_verify(request):
    """Second step of sign-in: a code from the authenticator app, or a recovery code."""
    user = request.user
    if user.is_verified() or not mfa.requires_mfa(user):
        return redirect(mfa.safe_next(request))
    if not mfa.has_confirmed_device(user):
        return redirect("accounts:mfa_setup")

    error = ""
    wait = mfa.locked_for(user)
    if request.method == "POST" and not wait:
        token = request.POST.get("token", "").strip().replace(" ", "")
        device = match_token(user, token) if token else None
        if device is not None:
            otp_login(request, device)
            return redirect(mfa.safe_next(request))
        mfa.record_failure(user)
        error = "That code is not valid."
        wait = mfa.locked_for(user)
    if wait:
        error = f"Too many attempts. Try again in about {max(1, -(-wait // 60))} minute(s)."
    return render(
        request,
        "accounts/mfa_verify.html",
        {"error": error, "next": request.GET.get("next") or request.POST.get("next", "")},
    )


@login_required
def mfa_setup(request):
    """First-time enrolment. Refused once a device exists, so someone who only knows the
    password can never add a second factor to an account that already has one."""
    user = request.user
    if not mfa.requires_mfa(user):
        return redirect("accounts:profile")
    if mfa.has_confirmed_device(user):
        return redirect("accounts:mfa_verify" if not user.is_verified() else "accounts:profile")

    device = None
    device_id = request.session.get(SETUP_SESSION_KEY)
    if device_id:
        device = TOTPDevice.objects.filter(pk=device_id, user=user, confirmed=False).first()
    if device is None:
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()
        device = TOTPDevice.objects.create(user=user, name="Authenticator app", confirmed=False)
        request.session[SETUP_SESSION_KEY] = device.pk

    error = ""
    if request.method == "POST":
        token = request.POST.get("token", "").strip().replace(" ", "")
        wait = mfa.locked_for(user)
        if wait:
            error = f"Too many attempts. Try again in about {max(1, -(-wait // 60))} minute(s)."
        elif token.isdigit() and device.verify_token(token):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            request.session.pop(SETUP_SESSION_KEY, None)
            otp_login(request, device)
            codes = mfa.issue_recovery_codes(user)
            return render(
                request,
                "accounts/mfa_recovery_codes.html",
                {"codes": codes, "next": mfa.safe_next(request), "first_time": True},
            )
        else:
            mfa.record_failure(user)
            error = "That code is not valid. Check the time on your phone and try again."
    return render(
        request,
        "accounts/mfa_setup.html",
        {
            "qr": mfa.qr_svg(mfa.provisioning_uri(device)),
            "secret": mfa.manual_secret(device),
            "error": error,
            "next": request.GET.get("next") or request.POST.get("next", ""),
        },
    )


@login_required
@require_POST
def mfa_regenerate_codes(request):
    """Replace the recovery codes. Needs a verified session (the middleware enforces it)."""
    if not request.user.is_verified():
        return redirect("accounts:mfa_verify")
    codes = mfa.issue_recovery_codes(request.user)
    messages.success(request, "New recovery codes generated. The old ones no longer work.")
    return render(
        request,
        "accounts/mfa_recovery_codes.html",
        {"codes": codes, "next": "/accounts/profile/", "first_time": False},
    )
