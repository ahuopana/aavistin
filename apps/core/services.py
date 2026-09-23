"""Welcome dashboard data: product overview widget and task widget, plus the
portfolio-wide Compliance Overview page.

See docs/architecture.md, "Dashboards".
"""

from collections import defaultdict

from django.db.models import Count
from django.urls import reverse

from apps.assessments.models import AssessmentStatus
from apps.orgs.models import Role
from apps.products.models import Configuration
from apps.products.services import compliance_ratio, editable_products, risk_ratio
from apps.risk.models import Control


def dashboard_products(user, limit=3):
    """Up to ``limit`` products the user can view, newest first.

    "Newest" stands in for "most recently updated" -- Product has no
    updated_at, and nothing rolls up activity across its configurations,
    assessments, risk register and evidence yet. Revisit with a real
    activity signal if this proxy turns out to be misleading in
    practice.
    """
    products = editable_products(user, role=None).order_by("-created_at")[:limit]
    return [
        {
            "product": product,
            "compliance": compliance_ratio(product),
            "risk": risk_ratio(product),
        }
        for product in products
    ]


def _ratio_fraction(ratio: tuple[int, int]) -> float:
    """A ratio with nothing to measure yet (0 total) sorts as if fully
    clean, not as a false alarm alongside genuinely bad ratios.
    """
    fulfilled, total = ratio
    return 1.0 if total == 0 else fulfilled / total


def compliance_overview(user):
    """Every product the user can view (uncapped), with its compliance
    and risk ratios, worst-compliance-first (risk as tiebreak) -- and
    the same two ratios summed across the whole portfolio.
    """
    products = editable_products(user, role=None).select_related(
        "product_family", "product_family__organisation"
    )

    rows = [
        {
            "product": product,
            "organisation": product.product_family.organisation,
            "family": product.product_family,
            "compliance": compliance_ratio(product),
            "risk": risk_ratio(product),
        }
        for product in products
    ]
    rows.sort(key=lambda r: (_ratio_fraction(r["compliance"]), _ratio_fraction(r["risk"])))

    totals_compliance = (
        sum(r["compliance"][0] for r in rows),
        sum(r["compliance"][1] for r in rows),
    )
    totals_risk = (sum(r["risk"][0] for r in rows), sum(r["risk"][1] for r in rows))

    return {
        "rows": rows,
        "totals": {"compliance": totals_compliance, "risk": totals_risk},
    }


def _candidate_tasks(user):
    products = editable_products(user, role=Role.EDITOR)

    configurations = Configuration.objects.filter(
        hardware_revision__hardware_variant__product__in=products
    ).select_related("hardware_revision__hardware_variant__product")

    tasks = []
    for configuration in configurations:
        assessment = configuration.assessments.order_by("-created_at").first()
        if assessment is None:
            tasks.append(
                {
                    "kind": "start_assessment",
                    "label": f"Start an assessment for {configuration.name}",
                    "url": reverse("assessments:configuration_detail", args=[configuration.pk]),
                    "sort_key": configuration.created_at,
                }
            )
        elif assessment.status == AssessmentStatus.DRAFT:
            tasks.append(
                {
                    "kind": "complete_assessment",
                    "label": f"Complete the assessment for {configuration.name}",
                    "url": reverse("assessments:assessment_detail", args=[assessment.pk]),
                    "sort_key": assessment.created_at,
                }
            )
        elif assessment.stale:
            tasks.append(
                {
                    "kind": "stale_assessment",
                    "label": f"Re-review the stale assessment for {configuration.name}",
                    "url": reverse("assessments:assessment_detail", args=[assessment.pk]),
                    "sort_key": assessment.created_at,
                }
            )

    controls = (
        Control.objects.filter(product__in=products)
        .annotate(evidence_link_count=Count("evidence_links"))
        .filter(evidence_link_count=0)
        .select_related("product")
    )
    for control in controls:
        tasks.append(
            {
                "kind": "provide_evidence",
                "label": f"Provide evidence for control: {control.name}",
                "url": reverse("evidence:product_list", args=[control.product_id]),
                "sort_key": control.created_at,
            }
        )

    return tasks


def dashboard_tasks(user, limit=3):
    """Up to ``limit`` pending-work suggestions, one per category where
    possible (oldest first within each), round-robined for variety
    rather than truly randomised -- a stable worklist beats a reshuffle
    on every page load.
    """
    by_kind = defaultdict(list)
    for task in _candidate_tasks(user):
        by_kind[task["kind"]].append(task)
    for group in by_kind.values():
        group.sort(key=lambda t: t["sort_key"])

    kinds = list(by_kind.keys())
    selected = []
    i = 0
    while len(selected) < limit and any(by_kind[k] for k in kinds):
        kind = kinds[i % len(kinds)]
        if by_kind[kind]:
            selected.append(by_kind[kind].pop(0))
        i += 1
    return selected


def product_tree(user):
    """Organisation > product family > product > (HW revision / SW
    release), for everything the user holds any role on -- unlike
    dashboard_products, not capped to 3.
    """
    products = (
        editable_products(user, role=None)
        .select_related("product_family__organisation")
        .prefetch_related("hw_variants__revisions", "sw_releases")
        .order_by("product_family__organisation__name", "product_family__name", "name")
    )

    organisations = {}
    for product in products:
        family = product.product_family
        organisation = family.organisation
        org_node = organisations.setdefault(
            organisation.id, {"organisation": organisation, "families": {}}
        )
        family_node = org_node["families"].setdefault(
            family.id, {"family": family, "products": []}
        )
        revisions = [
            f"{variant.name} rev {revision.label}"
            for variant in product.hw_variants.all()
            for revision in variant.revisions.all()
        ]
        releases = [release.version for release in product.sw_releases.all()]
        family_node["products"].append(
            {"product": product, "revisions": revisions, "releases": releases}
        )

    return [
        {"organisation": node["organisation"], "families": list(node["families"].values())}
        for node in organisations.values()
    ]
