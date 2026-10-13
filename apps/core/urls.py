from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("compliance/", views.compliance, name="compliance"),
    path("compare/", views.compare, name="compare"),
    path("approvals/", views.approvals, name="approvals"),
]
