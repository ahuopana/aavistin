from django.urls import path

from . import views

app_name = "risk"

urlpatterns = [
    path("configurations/<int:pk>/", views.register, name="register"),
    path("configurations/<int:pk>/entries/new/", views.entry_create, name="entry_create"),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/", views.entry_detail, name="entry_detail"
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/edit/",
        views.entry_edit,
        name="entry_edit",
    ),
]
