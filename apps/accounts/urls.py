from django.urls import path

from . import mfa_views, views

app_name = "accounts"

urlpatterns = [
    path("mfa/verify/", mfa_views.mfa_verify, name="mfa_verify"),
    path("mfa/setup/", mfa_views.mfa_setup, name="mfa_setup"),
    path("mfa/recovery-codes/", mfa_views.mfa_regenerate_codes, name="mfa_recovery_codes"),
    path("login/", views.ThrottledLoginView.as_view(), name="login"),
    path("profile/", views.profile, name="profile"),
    path("profile/password/", views.ProfilePasswordChangeView.as_view(), name="password_change"),
    path("profile/theme/", views.set_theme, name="theme"),
    path("avatar/<int:pk>/", views.avatar, name="avatar"),
]
