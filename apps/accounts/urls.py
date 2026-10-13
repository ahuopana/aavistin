from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("profile/theme/", views.set_theme, name="theme"),
    path("avatar/<int:pk>/", views.avatar, name="avatar"),
]
