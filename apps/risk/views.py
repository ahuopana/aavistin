"""Risk register UI: the register for one configuration (product baseline
plus matching deltas), a detail page per entry, and adding or editing
entries by hand.

Rating, treatment, deltas, suggestion review and approval come in later
slices; see docs/adr/0027-risk-entry-authoring.md.
"""

from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.http import urlencode
from django.views.decorators.http import require_POST

from apps.core.readiness import register_readiness
from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.products.models import Configuration, HardwareVariant, SoftwareOption, SoftwareRelease

from .consistency import check_threat_hazard_consistency
from .models import (
    AssetRating,
    CIAProperty,
    Control,
    ControlStatus,
    EntryType,
    ImpactCategory,
    Rating,
    RiskEntry,
    SuggestionStatus,
    ThreatConsequence,
    Treatment,
    TreatmentType,
)
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


def _approved_methods():
    return RequirementPackage.objects.filter(
        kind=PackageKind.METHOD, status=PackageStatus.APPROVED
    ).order_by("source")


def _methods() -> list[RequirementPackage]:
    return list(_approved_methods())


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
    ratings = {r.method_id: r for r in entry.ratings.all()}
    treatments = {t.method_id: t for t in entry.treatments.select_related("method")}
    applicable = applicable_methods(entry, methods)
    # Every applicable method gets a row (rated or not, so it can be rated),
    # plus any other approved method the entry already carries a rating under.
    row_methods = [m for m in methods if m in applicable or m.pk in ratings]
    method_rows = []
    for method in row_methods:
        rating = ratings.get(method.pk)
        treatment = treatments.get(method.pk)
        result = (
            evaluate_entry_rating(entry, method)
            if rating
            else {"severity": None, "likelihood": None, "level": None, "acceptance": None}
        )
        method_rows.append(
            {
                **result,
                "method": method,
                "rating": rating,
                "applicable": method in applicable,
                "severity_scale": _scale(method, "severity"),
                "likelihood_scale": _scale(method, "likelihood"),
                "treatment": treatment,
                "residual": evaluate_residual_rating(treatment) if treatment else None,
            }
        )

    asset_rows = []
    if entry.entry_type == EntryType.ASSET:
        current = {(r.method_id, r.property): r.severity for r in entry.asset_ratings.all()}
        for row in _asset_methods(methods):
            method = row["method"]
            asset_rows.append(
                {
                    "method": method,
                    "scale": _scale(method, "severity"),
                    "properties": [
                        {
                            "value": prop,
                            "label": prop.replace("_", " ").capitalize(),
                            "severity": current.get((method.pk, prop)),
                        }
                        for prop in row["properties"]
                    ],
                }
            )

    consequence_scale = (
        _scale((applicable or methods)[0], "severity") if (applicable or methods) else []
    )
    linked_controls = entry.controls.order_by("name")
    return render(
        request,
        "risk/entry_detail.html",
        {
            "configuration": configuration,
            "entry": entry,
            "scope": _scope_label(entry),
            "methods": methods,
            "method_rows": method_rows,
            "asset_rows": asset_rows,
            "asset_ratings": entry.asset_ratings.select_related("method"),
            "consequences": entry.consequences.select_related("hazard"),
            "consequence_scale": consequence_scale,
            "inherited_severity": inherited_severity(entry)
            if entry.entry_type == EntryType.THREAT
            else None,
            "impact_categories": ImpactCategory.choices,
            "hazard_categories": [ImpactCategory.SAFETY, ImpactCategory.PROPERTY_DAMAGE],
            "hazards": RiskEntry.objects.filter(product=entry.product, entry_type=EntryType.HAZARD)
            .exclude(suggestion_status=SuggestionStatus.DISMISSED)
            .order_by("label"),
            "treatment_types": TreatmentType.choices,
            "causes": entry.causes.select_related("threat"),
            "threats": entry.threats.exclude(suggestion_status=SuggestionStatus.DISMISSED),
            "controls": linked_controls,
            "available_controls": Control.objects.filter(product=entry.product)
            .exclude(pk__in=linked_controls.values("pk"))
            .order_by("name"),
            "control_statuses": ControlStatus.choices,
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


def _split_threat(entry: RiskEntry, prop: str, prop_label: str) -> RiskEntry:
    """One threat per violated property, sharing everything else; the label
    gains the property so the entries stay distinguishable in the register."""
    threat = RiskEntry(
        product=entry.product,
        entry_type=entry.entry_type,
        label=f"{entry.label} ({prop_label})",
        description=entry.description,
        asset=entry.asset,
        violates=prop,
        created_by=entry.created_by,
        **{field: getattr(entry, field) for field, _model, _lookup in SCOPE_FIELDS.values()},
    )
    threat._history_user = entry._history_user
    return threat


def _entry_form(request, configuration, entry: RiskEntry, *, is_new: bool):
    """Shared GET/POST handling for adding and editing an entry. On a
    validation error the form is shown again with what was typed."""
    product = entry.product
    # A delta or an entry that has deltas keeps its scope: moving either
    # would break the baseline/delta pairing apps.risk.resolution relies on.
    scope_locked = not is_new and (entry.base_entry_id or entry.deltas.exists())
    violates_choices = _violates_choices()
    # Keep an existing threat's property selectable even if its method is no
    # longer approved, so editing the label doesn't force a property change.
    if entry.violates and entry.violates not in {c["value"] for c in violates_choices}:
        violates_choices.append(
            {"value": entry.violates, "label": entry.violates.replace("_", " ").capitalize()}
        )

    if request.method == "POST":
        if is_new:
            entry.entry_type = request.POST.get("entry_type", "")
        entry.label = request.POST.get("label", "").strip()
        entry.description = request.POST.get("description", "").strip()
        is_threat = entry.entry_type == EntryType.THREAT
        # A new threat may name several properties: one entry is created per
        # property, since rating and treatment are per property. An existing
        # entry is a single threat, so editing posts exactly one.
        properties = list(dict.fromkeys(request.POST.getlist("violates"))) if is_threat else []
        if not is_new:
            properties = properties[:1]
        entry.violates = properties[0] if properties else ""
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
            property_labels = {c["value"]: c["label"] for c in violates_choices}
            if any(p not in property_labels for p in properties):
                raise ValidationError({"violates": "Choose a property from the risk methods."})
            if not scope_locked:
                _apply_scope(entry, request.POST.get("scope", ""))
            entry.full_clean()
            entries = (
                [_split_threat(entry, p, property_labels[p]) for p in properties]
                if len(properties) > 1
                else [entry]
            )
            for each in entries:
                each.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
        else:
            with transaction.atomic():
                for each in entries:
                    each.save()
            links = format_html_join(
                ", ",
                '<a href="{}">{}</a>',
                (
                    (reverse("risk:entry_detail", args=[configuration.pk, e.pk]), e.label)
                    for e in entries
                ),
            )
            if is_new and request.POST.get("next") == "another":
                # Keep type, scope and (for threats) asset so a run of
                # similar entries needs only a new label each time.
                django_messages.success(request, format_html("Added {}. Add the next one.", links))
                query = {"type": entry.entry_type, "scope": _scope_value(entry)}
                if entry.asset_id:
                    query["asset"] = entry.asset_id
                return redirect(
                    f"{reverse('risk:entry_create', args=[configuration.pk])}?{urlencode(query)}"
                )
            if len(entries) > 1:
                django_messages.success(
                    request, format_html("Added {} threats: {}.", len(entries), links)
                )
                return redirect(f"{reverse('risk:register', args=[configuration.pk])}?type=threat")
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
            "violates_choices": violates_choices,
            "violates_selected": properties
            if request.method == "POST" and is_threat
            else [entry.violates],
            "scope_choices": _scope_choices(product),
            "scope_value": request.POST.get("scope", "")
            if request.method == "POST" and not scope_locked
            else (request.GET.get("scope", "") if is_new else _scope_value(entry)),
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
    # Prefill from "Save and add another"; _entry_form re-validates on POST.
    asset_id = request.GET.get("asset", "")
    if request.method == "GET" and asset_id.isdigit():
        entry.asset = RiskEntry.objects.filter(
            pk=int(asset_id), product=product, entry_type=EntryType.ASSET
        ).first()
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


# --- Rating, consequences, treatment and controls --------------------------------
#
# Small POST-only forms on the entry page, in the flash-and-redirect shape of
# ADR 0010. See docs/adr/0028-risk-rating-and-treatment.md.


def _editable_entry(request, pk, entry_pk):
    """(configuration, entry) when the user may edit, else (None, redirect)."""
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    entry = get_object_or_404(RiskEntry, pk=entry_pk, product=product)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to change register entries.")
        return None, redirect("risk:entry_detail", pk=pk, entry_pk=entry_pk)
    return configuration, entry


def _back(configuration, entry, anchor=""):
    url = reverse("risk:entry_detail", args=[configuration.pk, entry.pk])
    return redirect(f"{url}#{anchor}" if anchor else url)


def _scale(method: RequirementPackage, kind: str) -> list[dict]:
    """[{value, label}] for a method's severity or likelihood scale."""
    spec = method.content.get(kind, {})
    low, high = spec.get("scale", [1, 5])
    labels = spec.get("labels", [])
    return [
        {
            "value": value,
            "label": f"{value} – {labels[value - low].replace('_', ' ')}"
            if value - low < len(labels)
            else str(value),
        }
        for value in range(low, high + 1)
    ]


def _in_scale(method: RequirementPackage, kind: str, raw: str, *, field: str) -> int | None:
    """Parse ``raw`` as a value on the method's scale; "" means not set."""
    if raw == "":
        return None
    low, high = method.content.get(kind, {}).get("scale", [1, 5])
    if not raw.isdigit() or not low <= int(raw) <= high:
        raise ValidationError({field: f"Choose a {kind} between {low} and {high}."})
    return int(raw)


def applicable_methods(entry: RiskEntry, methods) -> list[RequirementPackage]:
    """Methods an entry is rated under: a threat under each method that has its
    violated property; a hazard under each method without CIA properties (the
    safety-style methods), or every method if there is none."""
    if entry.entry_type == EntryType.THREAT:
        return [m for m in methods if entry.violates in m.content.get("properties", [])]
    if entry.entry_type == EntryType.HAZARD:
        cia = set(CIAProperty.values)
        safety = [m for m in methods if not cia & set(m.content.get("properties", []))]
        return safety or list(methods)
    return []


def _asset_methods(methods) -> list[dict]:
    """Methods with CIA properties, and which of those properties they rate."""
    rows = []
    for method in methods:
        props = [p for p in method.content.get("properties", []) if p in CIAProperty.values]
        if props:
            rows.append({"method": method, "properties": props})
    return rows


def inherited_severity(threat: RiskEntry) -> int | None:
    """The targeted asset's rating for the violated property, under the first
    applicable method that has one; a consequence defaults to it."""
    if not threat.asset_id or not threat.violates:
        return None
    ratings = {
        r.method_id: r.severity
        for r in AssetRating.objects.filter(entry=threat.asset, property=threat.violates)
    }
    for method in applicable_methods(threat, _methods()):
        if method.pk in ratings:
            return ratings[method.pk]
    return next(iter(ratings.values()), None)


@login_required
@require_POST
def asset_rating_save(request, pk, entry_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    method = get_object_or_404(_approved_methods(), pk=request.POST.get("method"))
    row = next((r for r in _asset_methods([method])), None)
    if entry.entry_type != EntryType.ASSET or row is None:
        django_messages.error(request, "Only assets are rated per property.")
        return _back(configuration, entry)
    try:
        values = {
            prop: _in_scale(method, "severity", request.POST.get(prop, ""), field=prop)
            for prop in row["properties"]
        }
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "rating")
    for prop, severity in values.items():
        if severity is None:
            AssetRating.objects.filter(entry=entry, method=method, property=prop).delete()
        else:
            AssetRating.objects.update_or_create(
                entry=entry, method=method, property=prop, defaults={"severity": severity}
            )
    django_messages.success(request, f"Asset rating under {method.source} saved.")
    return _back(configuration, entry, "rating")


@login_required
@require_POST
def rating_save(request, pk, entry_pk):
    """Likelihood (and, for hazards, severity) of an entry under one method."""
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    method = get_object_or_404(_approved_methods(), pk=request.POST.get("method"))
    if method not in applicable_methods(entry, _methods()):
        django_messages.error(request, f"{method.source} doesn't apply to this entry.")
        return _back(configuration, entry, "rating")
    try:
        likelihood = _in_scale(
            method, "likelihood", request.POST.get("likelihood", ""), field="likelihood"
        )
        severity = (
            _in_scale(method, "severity", request.POST.get("severity", ""), field="severity")
            if entry.entry_type == EntryType.HAZARD
            else None
        )
        if likelihood is None:
            Rating.objects.filter(entry=entry, method=method).delete()
            Treatment.objects.filter(entry=entry, method=method).delete()
            django_messages.success(request, f"Rating under {method.source} removed.")
            return _back(configuration, entry, "rating")
        rating = Rating.objects.filter(entry=entry, method=method).first() or Rating(
            entry=entry, method=method
        )
        rating.likelihood = likelihood
        rating.severity = severity
        rating.full_clean()
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "rating")
    rating.save()
    django_messages.success(request, f"Rating under {method.source} saved.")
    return _back(configuration, entry, "rating")


@login_required
@require_POST
def consequence_add(request, pk, entry_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    if entry.entry_type != EntryType.THREAT:
        django_messages.error(request, "Only threats have consequences.")
        return _back(configuration, entry)
    default = inherited_severity(entry)
    raw = request.POST.get("severity", "")
    hazard_id = request.POST.get("hazard", "")
    consequence = ThreatConsequence(
        threat=entry,
        impact_category=request.POST.get("impact_category", ""),
        override_justification=request.POST.get("override_justification", "").strip(),
        hazard=RiskEntry.objects.filter(
            pk=int(hazard_id), product=entry.product, entry_type=EntryType.HAZARD
        ).first()
        if hazard_id.isdigit()
        else None,
    )
    try:
        if not raw.isdigit():
            raise ValidationError({"severity": "Choose a severity."})
        consequence.severity = int(raw)
        # Inherits the asset's rating by default; anything else is an override.
        consequence.severity_is_override = default is not None and consequence.severity != default
        if hazard_id and consequence.hazard is None:
            raise ValidationError({"hazard": "Choose a hazard of this product."})
        consequence.full_clean()
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "consequences")
    consequence.save()
    django_messages.success(request, "Consequence added.")
    return _back(configuration, entry, "consequences")


@login_required
@require_POST
def consequence_delete(request, pk, entry_pk, consequence_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    get_object_or_404(ThreatConsequence, pk=consequence_pk, threat=entry).delete()
    django_messages.success(request, "Consequence removed.")
    return _back(configuration, entry, "consequences")


@login_required
@require_POST
def treatment_save(request, pk, entry_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    method = get_object_or_404(_approved_methods(), pk=request.POST.get("method"))
    if not Rating.objects.filter(entry=entry, method=method).exists():
        django_messages.error(request, f"Rate the entry under {method.source} first.")
        return _back(configuration, entry, "rating")
    treatment = Treatment.objects.filter(entry=entry, method=method).first() or Treatment(
        entry=entry, method=method
    )
    treatment.treatment_type = request.POST.get("treatment_type", "")
    treatment.justification = request.POST.get("justification", "").strip()
    treatment._history_user = request.user
    try:
        treatment.residual_severity = _in_scale(
            method,
            "severity",
            request.POST.get("residual_severity", ""),
            field="residual_severity",
        )
        treatment.residual_likelihood = _in_scale(
            method,
            "likelihood",
            request.POST.get("residual_likelihood", ""),
            field="residual_likelihood",
        )
        if (treatment.residual_severity is None) != (treatment.residual_likelihood is None):
            raise ValidationError(
                "Give both residual severity and likelihood, or neither (not assessed yet)."
            )
        treatment.full_clean()
        residual = evaluate_residual_rating(treatment)
        # Anything but mitigation is a decision someone must explain, and so is
        # a residual risk the method only accepts with a justification.
        needs_reason = treatment.treatment_type != TreatmentType.MITIGATE or residual[
            "acceptance"
        ] in ("justify", "must_treat")
        if needs_reason and not treatment.justification:
            raise ValidationError(
                {"justification": "Explain this treatment decision in the justification."}
            )
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "rating")
    treatment.save()
    django_messages.success(request, f"Treatment under {method.source} saved.")
    return _back(configuration, entry, "rating")


@login_required
@require_POST
def control_link(request, pk, entry_pk):
    """Link an existing control, or create a new one and link it."""
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    if entry.entry_type != EntryType.THREAT:
        django_messages.error(request, "Controls are linked to threats here.")
        return _back(configuration, entry)
    control_id = request.POST.get("control", "")
    if control_id.isdigit():
        control = get_object_or_404(Control, pk=int(control_id), product=entry.product)
    else:
        control = Control(
            product=entry.product,
            name=request.POST.get("name", "").strip(),
            description=request.POST.get("description", "").strip(),
            status=request.POST.get("status", ControlStatus.PLANNED),
        )
        control._history_user = request.user
        try:
            control.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return _back(configuration, entry, "controls")
        control.save()
    control.threats.add(entry)
    django_messages.success(request, f"Control “{control.name}” linked.")
    return _back(configuration, entry, "controls")


@login_required
@require_POST
def control_unlink(request, pk, entry_pk, control_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    control = get_object_or_404(Control, pk=control_pk, product=entry.product)
    control.threats.remove(entry)
    django_messages.success(request, f"Control “{control.name}” unlinked.")
    return _back(configuration, entry, "controls")


@login_required
@require_POST
def control_status(request, pk, entry_pk, control_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    control = get_object_or_404(Control, pk=control_pk, product=entry.product)
    control.status = request.POST.get("status", "")
    control._history_user = request.user
    try:
        control.full_clean()
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "controls")
    control.save()
    django_messages.success(request, f"“{control.name}” is now {control.get_status_display()}.")
    return _back(configuration, entry, "controls")


@login_required
def entry_delete(request, pk, entry_pk):
    """Confirm, then delete an entry with its ratings, consequences, causes and
    treatments. Threats targeting a deleted asset and consequences linking a
    deleted hazard are kept and unlinked; controls are kept."""
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    if entry.deltas.exists():
        django_messages.error(request, "This entry has configuration deltas; delete those first.")
        return _back(configuration, entry)
    if request.method == "POST":
        label = entry.label
        entry._history_user = request.user
        entry.delete()
        django_messages.success(request, f"Deleted “{label}”.")
        return redirect("risk:register", pk=configuration.pk)
    return render(
        request,
        "risk/entry_confirm_delete.html",
        {
            "configuration": configuration,
            "entry": entry,
            "ratings": entry.ratings.count() + entry.asset_ratings.count(),
            "treatments": entry.treatments.count(),
            "consequences": entry.consequences.count(),
            "causes": entry.causes.count(),
            "targeting_threats": entry.threats.all(),
            "linking_consequences": entry.threat_consequences.select_related("threat"),
            "controls": entry.controls.all(),
        },
    )
