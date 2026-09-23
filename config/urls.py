from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("orgs/", include("apps.orgs.urls")),
    path("assess/", include("apps.assessments.urls")),
    path("", include("apps.core.urls")),
]
