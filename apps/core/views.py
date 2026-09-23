from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .services import compliance_overview, dashboard_products, dashboard_tasks, product_tree


def home(request):
    if not request.user.is_authenticated:
        return render(request, "core/home.html")
    return render(
        request,
        "core/dashboard.html",
        {
            "products": dashboard_products(request.user),
            "tasks": dashboard_tasks(request.user),
            "tree": product_tree(request.user),
        },
    )


@login_required
def compliance(request):
    overview = compliance_overview(request.user)
    return render(request, "core/compliance.html", overview)
