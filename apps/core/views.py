from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from .compare import KINDS, build_subject, choice_label, diff_subjects, visible_objects
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


@login_required
def compare(request):
    """Compare two entities of one kind: products, hardware, releases,
    options, configurations or assessments (ADR 0035)."""
    kind = request.GET.get("kind", "configuration")
    if kind not in KINDS:
        raise Http404("Unknown kind")
    candidates = list(visible_objects(request.user, kind))
    options = sorted(
        ((o.pk, choice_label(kind, o)) for o in candidates), key=lambda x: x[1].lower()
    )

    by_pk = {o.pk: o for o in candidates}
    picked = []
    for key in ("a", "b"):
        raw = request.GET.get(key, "")
        picked.append(by_pk.get(int(raw)) if raw.isdigit() else None)
    first, second = picked

    diffs = subject_a = subject_b = None
    if first is not None and second is not None:
        subject_a, subject_b = build_subject(kind, first), build_subject(kind, second)
        diffs = diff_subjects(subject_a, subject_b)

    return render(
        request,
        "core/compare.html",
        {
            "kinds": [(key, label) for key, (label, _model) in KINDS.items()],
            "kind": kind,
            "kind_label": KINDS[kind][0],
            "options": options,
            "a": first.pk if first else None,
            "b": second.pk if second else None,
            "subject_a": subject_a,
            "subject_b": subject_b,
            "diffs": diffs,
            "differences": sum(d.differences for d in diffs) if diffs is not None else 0,
            "same_pick": first is not None and first == second,
        },
    )
