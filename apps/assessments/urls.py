from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("configurations/<int:pk>/", views.configuration_detail, name="configuration_detail"),
    path("configurations/<int:pk>/answer/", views.answer_question, name="answer_question"),
    path(
        "configurations/<int:pk>/assessments/new/",
        views.assessment_create,
        name="assessment_create",
    ),
    path("assessments/<int:pk>/", views.assessment_detail, name="assessment_detail"),
    path("assessments/<int:pk>/approve/", views.assessment_approve, name="assessment_approve"),
]
