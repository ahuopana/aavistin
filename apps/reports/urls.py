from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list, name="list"),
    path("configuration/<int:configuration_pk>/", views.report_generate, name="generate"),
    path("<str:report_id>/", views.report_detail, name="detail"),
    path("<str:report_id>/pdf/", views.report_pdf, name="pdf"),
]
