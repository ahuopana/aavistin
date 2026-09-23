from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("orgs/", include("apps.orgs.urls")),
    path("products/", include("apps.products.urls")),
    path("assess/", include("apps.assessments.urls")),
    path("evidence/", include("apps.evidence.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
