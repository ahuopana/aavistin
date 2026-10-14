from django.contrib import admin
from django.urls import include, path

from apps.reports import views as report_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("orgs/", include("apps.orgs.urls")),
    path("products/", include("apps.products.urls")),
    path("assess/", include("apps.assessments.urls")),
    path("risk/", include("apps.risk.urls")),
    path("evidence/", include("apps.evidence.urls")),
    path("reports/", include("apps.reports.urls")),
    path("verify/<str:report_id>/", report_views.verify, name="verify"),
    path("guide/", include("apps.userguide.urls")),
    path("", include("apps.core.urls")),
]
