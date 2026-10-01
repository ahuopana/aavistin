"""Read-only risk register UI: the register for one configuration (product
baseline plus matching deltas) and a detail page per entry.

Editing, suggestions, treatment and approval come in later slices; these
views only present what ``resolution`` and ``rating`` already compute.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.products.models import Configuration

from .consistency import check_threat_hazard_consistency
from .models import EntryType, RiskEntry, SuggestionStatus
from .rating import evaluate_entry_rating, evaluate_residual_rating
from .resolution import register_for_configuration
from .suggestions import pending_suggestions

TYPE_ORDER = [EntryType.ASSET, EntryType.THREAT, EntryType.HAZARD]


def _scope_label(entry: RiskEntry) -> str:
    if entry.scope_hardware_variant_id:
        scope = f"HW variant {entry.scope_hardware_variant.name}"
    elif entry.scope_software_release_id:
        scope = f"SW release {entry.scope_software_release.version}"
    elif entry.scope_software_option_id:
        scope = f"Option {entry.scope_software_option.name}"
    else:
        return "Baseline"
    return f"Delta · {scope}" if entry.base_entry_id else f"Added · {scope}"


def _methods() -> list[RequirementPackage]:
    return list(
        RequirementPackage.objects.filter(
            kind=PackageKind.METHOD, status=PackageStatus.APPROVED
        ).order_by("source")
    )


def _rating_cells(entry: RiskEntry, methods) -> list[dict]:
    """One cell per method the entry is rated under, in method order."""
    if entry.entry_type == EntryType.ASSET:
        return []
    rated = {r.method_id: r for r in entry.ratings.all()}
    cells = []
    for method in methods:
        if method.pk not in rated:
            continue
        result = evaluate_entry_rating(entry, method)
        cells.append({"method": method.source, **result})
    return cells


def _entry_row(entry: RiskEntry, methods) -> dict:
    return {
        "entry": entry,
        "scope": _scope_label(entry),
        "ratings": _rating_cells(entry, methods),
        "controls": entry.controls.count(),
        "issues": (
            check_threat_hazard_consistency(entry) if entry.entry_type == EntryType.THREAT else []
        ),
    }


@login_required
def register(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    methods = _methods()

    entries = register_for_configuration(configuration)
    entry_type = request.GET.get("type", "")
    query = request.GET.get("q", "").strip().lower()
    shown = [
        e
        for e in entries
        if (not entry_type or e.entry_type == entry_type)
        and (not query or query in e.label.lower() or query in e.description.lower())
    ]
    shown.sort(key=lambda e: (TYPE_ORDER.index(e.entry_type), e.label))
    prefetched = {
        e.pk: e
        for e in RiskEntry.objects.filter(pk__in=[e.pk for e in shown])
        .select_related(
            "asset", "scope_hardware_variant", "scope_software_release", "scope_software_option"
        )
        .prefetch_related("ratings", "consequences", "controls", "treatments")
    }
    rows = [_entry_row(prefetched[e.pk], methods) for e in shown]

    sections = [
        {
            "type": t,
            "label": t.label + "s",
            "rows": [r for r in rows if r["entry"].entry_type == t],
        }
        for t in TYPE_ORDER
    ]
    counts = {t.value: sum(1 for e in entries if e.entry_type == t) for t in TYPE_ORDER}

    return render(
        request,
        "risk/register.html",
        {
            "configuration": configuration,
            "product": product,
            "sections": [s for s in sections if s["rows"]],
            "counts": counts,
            "total": len(entries),
            "pending_suggestions": len(pending_suggestions(configuration)),
            "must_treat": sum(
                1 for r in rows for c in r["ratings"] if c["acceptance"] == "must_treat"
            ),
            "unrated": sum(
                1 for r in rows if r["entry"].entry_type != EntryType.ASSET and not r["ratings"]
            ),
            "issue_count": sum(len(r["issues"]) for r in rows),
            "type_filter": entry_type,
            "query": request.GET.get("q", ""),
            "entry_types": TYPE_ORDER,
            "can_edit": has_role(request.user, Role.EDITOR, product_family=product.product_family),
        },
    )


@login_required
def entry_detail(request, pk, entry_pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    entry = get_object_or_404(
        RiskEntry.objects.select_related(
            "asset",
            "base_entry",
            "scope_hardware_variant",
            "scope_software_release",
            "scope_software_option",
        ),
        pk=entry_pk,
        product=configuration.hardware_revision.hardware_variant.product,
    )
    methods = _methods()
    treatments = {t.method_id: t for t in entry.treatments.select_related("method")}
    method_rows = []
    for cell in _rating_cells(entry, methods):
        method = next(m for m in methods if m.source == cell["method"])
        treatment = treatments.get(method.pk)
        method_rows.append(
            {
                **cell,
                "treatment": treatment,
                "residual": evaluate_residual_rating(treatment) if treatment else None,
            }
        )
    return render(
        request,
        "risk/entry_detail.html",
        {
            "configuration": configuration,
            "entry": entry,
            "scope": _scope_label(entry),
            "method_rows": method_rows,
            "asset_ratings": entry.asset_ratings.select_related("method"),
            "consequences": entry.consequences.select_related("hazard"),
            "causes": entry.causes.select_related("threat"),
            "threats": entry.threats.exclude(suggestion_status=SuggestionStatus.DISMISSED),
            "controls": entry.controls.all(),
            "deltas": entry.deltas.all(),
            "issues": (
                check_threat_hazard_consistency(entry)
                if entry.entry_type == EntryType.THREAT
                else []
            ),
        },
    )
