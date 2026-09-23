"""Welcome dashboard data: product overview widget and task widget.

See docs/architecture.md, "Dashboards".
"""

from collections import defaultdict

from django.db.models import Count
from django.urls import reverse

from apps.assessments.evaluation import evaluate_configuration
from apps.assessments.models import AssessmentStatus
from apps.orgs.models import Role
from apps.products.models import Configuration
from apps.products.services import editable_products
from apps.risk.models import Control, EntryType, RiskEntry
from apps.risk.rating import evaluate_residual_rating

ACCEPTABLE = ("accept", "justify")


def compliance_ratio(product) -> tuple[int, int]:
    """(fulfilled, total) in-scope requirements across the product's
    configurations' current evaluation (live, not frozen to an approved
    snapshot). A requirement counts as fulfilled unless its package has
    an unresolved action-required finding in that evaluation -- findings
    aren't tracked per requirement, only per package, so this is a
    package-level proxy, not a true per-requirement pass/fail.
    """
    total: set[tuple[str, str, str]] = set()
    bad: set[tuple[str, str, str]] = set()

    configurations = Configuration.objects.filter(
        hardware_revision__hardware_variant__product=product
    )
    for configuration in configurations:
        evaluation = evaluate_configuration(configuration)
        blocking_packages = {
            (f["source"], f["version"])
            for f in evaluation["findings"]
            if f["level"] == "action_required"
        }
        for result in evaluation["results"]:
            if not result["in_scope"]:
                continue
            package_key = (result["source"], result["version"])
            for requirement_id in result["requirements"]:
                key = (*package_key, requirement_id)
                total.add(key)
                if package_key in blocking_packages:
                    bad.add(key)

    return len(total - bad), len(total)


def risk_ratio(product) -> tuple[int, int]:
    """(acceptable, total) baseline threat/hazard entries, where
    "acceptable" means every method treatment on the entry has a
    residual acceptance of "accept" or "justify" -- an entry with no
    treatment yet, or one still rated "must_treat" under any method,
    doesn't count.
    """
    entries = RiskEntry.objects.filter(
        product=product,
        entry_type__in=[EntryType.THREAT, EntryType.HAZARD],
        scope_hardware_variant__isnull=True,
        scope_software_release__isnull=True,
        scope_software_option__isnull=True,
    ).prefetch_related("treatments__method")

    total = 0
    acceptable = 0
    for entry in entries:
        total += 1
        treatments = list(entry.treatments.all())
        if treatments and all(
            evaluate_residual_rating(t)["acceptance"] in ACCEPTABLE for t in treatments
        ):
            acceptable += 1
    return acceptable, total


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
