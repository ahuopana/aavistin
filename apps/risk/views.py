"""Risk register UI: the register for one configuration (product baseline
plus matching deltas), a detail page per entry, and adding or editing
entries by hand.

Rating, treatment, deltas, suggestion review and approval come in later
slices; see docs/adr/0027-risk-entry-authoring.md.
"""

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.readiness import register_readiness
from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.products.models import Configuration, HardwareVariant, SoftwareOption, SoftwareRelease

from .consistency import check_threat_hazard_consistency
from .models import CIAProperty, EntryType, RiskEntry, SuggestionStatus
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

    pending_count = len(pending_suggestions(configuration))
    return render(
        request,
        "risk/register.html",
        {
            "readiness": register_readiness(configuration, pending_suggestions=pending_count)
            if not entries
            else [],
            "configuration": configuration,
            "product": product,
            "sections": [s for s in sections if s["rows"]],
            "counts": counts,
            "total": len(entries),
            "pending_suggestions": pending_count,
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
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
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
            "can_edit": has_role(request.user, Role.EDITOR, product=entry.product),
        },
    )


# Scope is one <select>: "" for the product baseline, or "<kind>:<pk>"
# for exactly one HW variant, SW release or SW option (RiskEntry.clean()
# allows at most one).
SCOPE_FIELDS = {
    "hw": ("scope_hardware_variant", HardwareVariant, "product"),
    "sw": ("scope_software_release", SoftwareRelease, "product"),
    "opt": ("scope_software_option", SoftwareOption, "software_release__product"),
}


def _scope_choices(product) -> list[dict]:
    return [
        {"value": "", "label": "Baseline (every configuration)"},
        *(
            {"value": f"hw:{v.pk}", "label": f"HW variant {v.name}"}
            for v in HardwareVariant.objects.filter(product=product).order_by("name")
        ),
        *(
            {"value": f"sw:{r.pk}", "label": f"SW release {r.version}"}
            for r in SoftwareRelease.objects.filter(product=product).order_by("version")
        ),
        *(
            {"value": f"opt:{o.pk}", "label": f"Option {o.name} ({o.software_release.version})"}
            for o in SoftwareOption.objects.filter(software_release__product=product)
            .select_related("software_release")
            .order_by("software_release__version", "name")
        ),
    ]


def _scope_value(entry: RiskEntry) -> str:
    for kind, (field, _model, _lookup) in SCOPE_FIELDS.items():
        pk = getattr(entry, f"{field}_id")
        if pk:
            return f"{kind}:{pk}"
    return ""


def _apply_scope(entry: RiskEntry, value: str) -> None:
    for field, _model, _lookup in SCOPE_FIELDS.values():
        setattr(entry, field, None)
    if not value:
        return
    kind, _, pk = value.partition(":")
    if kind not in SCOPE_FIELDS or not pk.isdigit():
        raise ValidationError("Choose a valid scope.")
    field, model, product_lookup = SCOPE_FIELDS[kind]
    target = model.objects.filter(pk=int(pk), **{product_lookup: entry.product}).first()
    if target is None:
        raise ValidationError("Choose a valid scope.")
    setattr(entry, field, target)


def _violates_choices() -> list[dict]:
    """Properties a threat can violate: those of the approved methods, in
    method order, falling back to CIA when no method is approved yet."""
    properties: list[str] = []
    for method in _methods():
        for prop in method.content.get("properties", []):
            if prop not in properties:
                properties.append(prop)
    if not properties:
        properties = list(CIAProperty.values)
    return [{"value": p, "label": p.replace("_", " ").capitalize()} for p in properties]


def _flash_errors(request, exc: ValidationError) -> None:
    if hasattr(exc, "message_dict"):
        for messages in exc.message_dict.values():
            for message in messages:
                django_messages.error(request, message)
    else:
        for message in exc.messages:
            django_messages.error(request, message)


def _entry_form(request, configuration, entry: RiskEntry, *, is_new: bool):
    """Shared GET/POST handling for adding and editing an entry. On a
    validation error the form is shown again with what was typed."""
    product = entry.product
    # A delta or an entry that has deltas keeps its scope: moving either
    # would break the baseline/delta pairing apps.risk.resolution relies on.
    scope_locked = not is_new and (entry.base_entry_id or entry.deltas.exists())

    if request.method == "POST":
        if is_new:
            entry.entry_type = request.POST.get("entry_type", "")
        entry.label = request.POST.get("label", "").strip()
        entry.description = request.POST.get("description", "").strip()
        is_threat = entry.entry_type == EntryType.THREAT
        entry.violates = request.POST.get("violates", "") if is_threat else ""
        asset_id = request.POST.get("asset", "") if is_threat else ""
        entry.asset = (
            RiskEntry.objects.filter(
                pk=int(asset_id), product=product, entry_type=EntryType.ASSET
            ).first()
            if asset_id.isdigit()
            else None
        )
        entry._history_user = request.user
        try:
            if entry.entry_type not in EntryType.values:
                raise ValidationError({"entry_type": "Choose an entry type."})
            if is_threat and asset_id and entry.asset is None:
                raise ValidationError({"asset": "Choose an asset of this product."})
            if not scope_locked:
                _apply_scope(entry, request.POST.get("scope", ""))
            entry.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
        else:
            entry.save()
            django_messages.success(request, "Entry added." if is_new else "Entry updated.")
            return redirect("risk:entry_detail", pk=configuration.pk, entry_pk=entry.pk)

    return render(
        request,
        "risk/entry_form.html",
        {
            "configuration": configuration,
            "entry": entry,
            "is_new": is_new,
            "entry_types": TYPE_ORDER,
            "assets": RiskEntry.objects.filter(product=product, entry_type=EntryType.ASSET)
            .exclude(suggestion_status=SuggestionStatus.DISMISSED)
            .exclude(pk=entry.pk or 0)
            .order_by("label"),
            "violates_choices": _violates_choices(),
            "scope_choices": _scope_choices(product),
            "scope_value": request.POST.get("scope", "")
            if request.method == "POST" and not scope_locked
            else _scope_value(entry),
            "scope_locked": scope_locked,
        },
    )


@login_required
def entry_create(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add register entries.")
        return redirect("risk:register", pk=pk)
    entry = RiskEntry(
        product=product,
        entry_type=request.GET.get("type", EntryType.THREAT)
        if request.GET.get("type") in EntryType.values
        else EntryType.THREAT,
        created_by=request.user,
    )
    return _entry_form(request, configuration, entry, is_new=True)


@login_required
def entry_edit(request, pk, entry_pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    entry = get_object_or_404(RiskEntry, pk=entry_pk, product=product)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit register entries.")
        return redirect("risk:entry_detail", pk=pk, entry_pk=entry_pk)
    return _entry_form(request, configuration, entry, is_new=False)
