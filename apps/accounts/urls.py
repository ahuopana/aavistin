from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("profile/password/", views.ProfilePasswordChangeView.as_view(), name="password_change"),
    path("profile/theme/", views.set_theme, name="theme"),
    path("avatar/<int:pk>/", views.avatar, name="avatar"),
]
