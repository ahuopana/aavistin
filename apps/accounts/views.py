from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import avatars
from .forms import ProfileForm
from .models import Theme
from .prefs import effective_time_zone, get_profile

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
