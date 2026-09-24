from django.urls import path

from . import views

app_name = "orgs"

urlpatterns = [
    path("", views.organisation_list, name="list"),
    path("portfolio/", views.portfolio, name="portfolio"),
    path("<slug:slug>/", views.organisation_detail, name="detail"),
]
