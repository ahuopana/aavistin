from django.urls import path

from . import views

app_name = "products"

urlpatterns = [
    path("families/<int:family_id>/products/new/", views.product_create, name="product_create"),
    path("<int:pk>/", views.product_detail, name="product_detail"),
    path("<int:pk>/edit/", views.product_edit, name="product_edit"),
    path(
        "<int:product_id>/hardware/new/",
        views.hardware_variant_create,
        name="hardware_variant_create",
    ),
    path(
        "hardware-variants/<int:pk>/edit/",
        views.hardware_variant_edit,
        name="hardware_variant_edit",
    ),
    path(
        "hardware-variants/<int:variant_id>/revisions/new/",
        views.hardware_revision_create,
        name="hardware_revision_create",
    ),
    path(
        "hardware-revisions/<int:pk>/edit/",
        views.hardware_revision_edit,
        name="hardware_revision_edit",
    ),
    path(
        "<int:product_id>/software/new/",
        views.software_release_create,
        name="software_release_create",
    ),
    path(
        "software-releases/<int:pk>/edit/",
        views.software_release_edit,
        name="software_release_edit",
    ),
    path(
        "software-releases/<int:release_id>/options/new/",
        views.software_option_create,
        name="software_option_create",
    ),
    path(
        "software-options/<int:pk>/edit/",
        views.software_option_edit,
        name="software_option_edit",
    ),
    path(
        "<int:product_id>/configurations/new/",
        views.configuration_create,
        name="configuration_create",
    ),
    path(
        "configurations/<int:pk>/edit/",
        views.configuration_edit,
        name="configuration_edit",
    ),
    path("<str:model_name>/<int:pk>/approve/", views.entity_approve, name="entity_approve"),
    path("<str:model_name>/<int:pk>/delete/", views.entity_delete, name="entity_delete"),
]
