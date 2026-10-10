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
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/delete/",
        views.entry_delete,
        name="entry_delete",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/asset-rating/",
        views.asset_rating_save,
        name="asset_rating_save",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/rating/",
        views.rating_save,
        name="rating_save",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/treatment/",
        views.treatment_save,
        name="treatment_save",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/consequences/",
        views.consequence_add,
        name="consequence_add",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/consequences/<int:consequence_pk>/delete/",
        views.consequence_delete,
        name="consequence_delete",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/controls/",
        views.control_link,
        name="control_link",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/controls/<int:control_pk>/unlink/",
        views.control_unlink,
        name="control_unlink",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/controls/<int:control_pk>/status/",
        views.control_status,
        name="control_status",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/causes/",
        views.cause_add,
        name="cause_add",
    ),
    path(
        "configurations/<int:pk>/entries/<int:entry_pk>/causes/<int:cause_pk>/delete/",
        views.cause_delete,
        name="cause_delete",
    ),
    path("configurations/<int:pk>/suggestions/", views.suggestions, name="suggestions"),
    path(
        "configurations/<int:pk>/suggestions/accept/",
        views.suggestion_accept,
        name="suggestion_accept",
    ),
    path(
        "configurations/<int:pk>/suggestions/dismiss/",
        views.suggestion_dismiss,
        name="suggestion_dismiss",
    ),
    path(
        "configurations/<int:pk>/suggestions/<int:entry_pk>/restore/",
        views.suggestion_restore,
        name="suggestion_restore",
    ),
]
