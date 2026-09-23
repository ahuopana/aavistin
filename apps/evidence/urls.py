from django.urls import path

from . import views

app_name = "evidence"

urlpatterns = [
    path("products/<int:product_pk>/", views.product_evidence_list, name="product_list"),
    path("products/<int:product_pk>/new/", views.evidence_create, name="create"),
    path("<int:pk>/", views.evidence_detail, name="detail"),
    path("<int:pk>/link-control/", views.evidence_link_control, name="link_control"),
    path("<int:pk>/link-requirement/", views.evidence_link_requirement, name="link_requirement"),
    path("<int:pk>/delete/", views.evidence_delete, name="delete"),
    path("links/<int:link_pk>/unlink/", views.evidence_unlink, name="unlink"),
]
