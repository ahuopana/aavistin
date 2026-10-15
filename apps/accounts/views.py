from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.orgs.services import role_grants_for_user

from . import avatars
from .forms import ProfileForm
from .models import AuthSource, Theme
from .prefs import effective_time_zone, get_profile
from .throttle import lockout_seconds

User = get_user_model()


@login_required
def profile(request):
    profile = get_profile(request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, user=request.user, profile=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile saved.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(user=request.user, profile=profile)
    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
            "now": timezone.now(),
            "time_zone": effective_time_zone(profile),
            "grants": role_grants_for_user(request.user),
            "can_change_password": request.user.auth_source == AuthSource.LOCAL,
        },
    )


@login_required
@require_POST
def set_theme(request):
    """Persist the header toggle so the choice follows the user across browsers."""
    theme = request.POST.get("theme")
    if theme not in Theme.values:
        return HttpResponseBadRequest("Unknown theme.")
    profile = get_profile(request.user)
    profile.theme = theme
    profile.save(update_fields=["theme"])
    return JsonResponse({"theme": theme})


@login_required
def avatar(request, pk):
    user = get_object_or_404(User, pk=pk)
    profile = get_profile(user)
    if not (
        avatars.uploads_enabled() and profile.avatar and default_storage.exists(profile.avatar)
    ):
        raise Http404("No avatar.")
    response = FileResponse(default_storage.open(profile.avatar, "rb"), content_type="image/png")
    response["Cache-Control"] = "private, max-age=86400"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class ProfilePasswordChangeView(PasswordChangeView):
    """Password change for local accounts; directory users change it at the source."""

    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("accounts:profile")

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.auth_source != AuthSource.LOCAL:
            messages.error(
                request,
                f"Your password is managed by {request.user.get_auth_source_display()}.",
            )
            return redirect("accounts:profile")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, "Password changed.")
        return super().form_valid(form)


class ThrottledLoginView(LoginView):
    """The sign-in page; tells the user when failed attempts have locked sign-in."""

    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.method == "POST":
            wait = lockout_seconds(self.request, self.request.POST.get("username", ""))
            if wait:
                context["locked_minutes"] = max(1, -(-wait // 60))
        return context
