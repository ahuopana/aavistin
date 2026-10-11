from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .navigation import approval_items, is_approver_anywhere
from .services import compliance_overview, dashboard_products, dashboard_tasks, product_tree

DASHBOARD_APPROVALS = 5


def home(request):
    if not request.user.is_authenticated:
        return render(request, "core/home.html")
    approvals = None
    if is_approver_anywhere(request.user):
        items = [
            {**item, "product": group["product"]}
            for group in approval_items(request.user)
            for item in group["items"]
        ]
        approvals = {"items": items[:DASHBOARD_APPROVALS], "total": len(items)}
    return render(
        request,
        "core/dashboard.html",
        {
            "approvals": approvals,
            "products": dashboard_products(request.user),
            "tasks": dashboard_tasks(request.user),
            "tree": product_tree(request.user),
        },
    )


@login_required
def compliance(request):
    overview = compliance_overview(request.user)
    return render(request, "core/compliance.html", overview)


@login_required
def approvals(request):
    """Everything the user could approve now, grouped by product (ADR 0032)."""
    groups = approval_items(request.user)
    return render(
        request,
        "core/approvals.html",
        {
            "groups": groups,
            "total": sum(len(g["items"]) for g in groups),
            "is_approver": is_approver_anywhere(request.user),
        },
    )
