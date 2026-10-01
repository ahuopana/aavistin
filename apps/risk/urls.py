from django.urls import path

from . import views

app_name = "risk"

urlpatterns = [
    path("configurations/<int:pk>/", views.register, name="register"),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/", views.entry_detail, name="entry_detail"
    ),
]
