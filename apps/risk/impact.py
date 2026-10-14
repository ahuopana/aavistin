"""Impact categories come from risk method packages (ADR 0034).

A method package may declare ``impact_categories``: ``[{"id", "label",
"description"?, "links_to_hazard"?}]``. A threat's consequences can use the
categories of the approved methods that rate it. A method that declares none
gets ``DEFAULT_CATEGORIES``, the set every method had before categories
moved into packages, so existing method packages keep working unchanged.

``links_to_hazard`` marks harm to people or property: such a consequence may
link a hazard entry, and the cross-method consistency rules apply to it.
"""

from apps.packages.models import PackageKind, PackageStatus, RequirementPackage

DEFAULT_CATEGORIES = [
    {"id": "safety", "label": "Safety (people)", "links_to_hazard": True},
    {"id": "property_damage", "label": "Property damage", "links_to_hazard": True},
    {"id": "operational", "label": "Operational"},
    {"id": "financial", "label": "Financial"},
    {"id": "privacy", "label": "Privacy"},
]


def method_categories(method) -> list[dict]:
    """The categories ``method`` declares, or the defaults when it declares none."""
    return method.content.get("impact_categories") or DEFAULT_CATEGORIES


def merged_categories(methods) -> list[dict]:
    """Categories of ``methods`` in declaration order, first definition wins;
    the defaults when ``methods`` is empty."""
    merged: dict[str, dict] = {}
    for method in methods:
        for category in method_categories(method):
            merged.setdefault(category["id"], category)
    return list(merged.values()) if merged else list(DEFAULT_CATEGORIES)


def approved_methods():
    return RequirementPackage.objects.filter(
        kind=PackageKind.METHOD, status=PackageStatus.APPROVED
    ).order_by("source")


def all_categories() -> list[dict]:
    """Every category of every approved method (for labels and rules)."""
    return merged_categories(approved_methods())


def hazard_linkable_ids() -> set[str]:
    return {c["id"] for c in all_categories() if c.get("links_to_hazard")}


def category_label(category_id: str) -> str:
    """Label of ``category_id``; a readable form of the id if no approved
    method declares it any more (e.g. after a method version dropped it)."""
    for category in all_categories() + DEFAULT_CATEGORIES:
        if category["id"] == category_id:
            return category["label"]
    return category_id.replace("_", " ").capitalize()
