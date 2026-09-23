from django.shortcuts import render

from .services import dashboard_products, dashboard_tasks


def home(request):
    if not request.user.is_authenticated:
        return render(request, "core/home.html")
    return render(
        request,
        "core/dashboard.html",
        {
            "products": dashboard_products(request.user),
            "tasks": dashboard_tasks(request.user),
        },
    )
