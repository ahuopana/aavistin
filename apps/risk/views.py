"""Risk register UI: the register for one configuration (product baseline
plus matching deltas), a detail page per entry, and adding or editing
entries by hand.

Rating, treatment, causes, controls, suggestion review and approval of
the configuration's register view follow; deltas are still admin-only.
See docs/adr/0027-risk-entry-authoring.md, 0028-risk-rating-and-treatment.md,
0029-hazard-causes-and-suggestion-review.md and
0032-navigation-and-workflow-guidance.md.
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

from apps.core.navigation import breadcrumbs, configuration_workflow, latest_risk_assessment
from apps.core.readiness import register_readiness
from apps.orgs.models import Role
from apps.orgs.services import has_role
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.products.models import Configuration, HardwareVariant, SoftwareOption, SoftwareRelease

from . import mitigation
from .approval import RiskAssessmentError, approve_risk_assessment
from .consistency import check_threat_hazard_consistency
from .impact import hazard_linkable_ids, merged_categories
from .mitigation import mitigation_controls, mitigation_state
from .models import (
    AssetRating,
    CauseType,
    CIAProperty,
    Control,
    ControlStatus,
    EntryType,
    HazardCause,
    Rating,
    RiskAssessment,
    RiskAssessmentStatus,
    RiskEntry,
    SuggestionStatus,
    ThreatConsequence,
    Treatment,
    TreatmentType,
)
from .rating import evaluate_entry_rating, evaluate_residual_rating
from .resolution import register_for_configuration
from .suggestions import accept_suggestion, dismiss_suggestion, pending_suggestions

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

    pending = pending_suggestions(configuration)
    pending_count = len(pending)
    workflow = configuration_workflow(
        configuration, request.user, entries=entries, pending=pending
    )
    return render(
        request,
        "risk/register.html",
        {
            "crumbs": breadcrumbs(configuration=configuration, trail=[("Risk register", None)]),
            "workflow": workflow,
            "risk_assessment": workflow["risk_assessment"],
            "risk_state": workflow["risk_state"],
            "can_approve": has_role(request.user, Role.APPROVER, product=product),
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
    controls_for_mitigation = mitigation_controls(entry)
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
                "mitigation": (
                    state := mitigation_state(treatment, controls_for_mitigation)
                    if treatment
                    else None
                ),
                "mitigation_label": mitigation.LABELS.get(state),
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
    product_controls = list(Control.objects.filter(product=entry.product).order_by("name"))
    cause_rows = []
    if entry.entry_type == EntryType.HAZARD:
        for cause in entry.causes.select_related("threat").prefetch_related("controls"):
            linked = list(cause.controls.order_by("name"))
            cause_rows.append(
                {
                    "cause": cause,
                    "controls": linked,
                    "available": [c for c in product_controls if c not in linked],
                }
            )
    return render(
        request,
        "risk/entry_detail.html",
        {
            "crumbs": breadcrumbs(
                configuration=configuration,
                trail=[
                    ("Risk register", reverse("risk:register", args=[configuration.pk])),
                    (entry.label, None),
                ],
            ),
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
            # From the threat's rating methods (ADR 0034).
            "impact_categories": merged_categories(applicable),
            "hazard_categories": sorted(hazard_linkable_ids()),
            "hazards": RiskEntry.objects.filter(product=entry.product, entry_type=EntryType.HAZARD)
            .exclude(suggestion_status=SuggestionStatus.DISMISSED)
            .order_by("label"),
            "treatment_types": TreatmentType.choices,
            "causes": entry.causes.select_related("threat"),
            "cause_rows": cause_rows,
            "cause_types": CauseType.choices,
            "product_threats": RiskEntry.objects.filter(
                product=entry.product, entry_type=EntryType.THREAT
            )
            .exclude(suggestion_status=SuggestionStatus.DISMISSED)
            .order_by("label"),
            "missing_cyber_cause": _missing_cyber_cause(entry),
            # A catalog hazard's suggested controls have no automatic target
            # (they belong to a cause), so they are listed as a hint.
            "catalog_controls": [
                name
                for name in _catalog_entry(entry).get("suggested_controls", [])
                if entry.entry_type == EntryType.HAZARD
                and not any(name == c.name for row in cause_rows for c in row["controls"])
            ],
            "threats": entry.threats.exclude(suggestion_status=SuggestionStatus.DISMISSED),
            "controls": linked_controls,
            "available_controls": [c for c in product_controls if c not in linked_controls],
            # The treatment form's control picker (ADR 0033).
            "product_controls": product_controls,
            "threat_control_ids": {c.pk for c in linked_controls},
            "mitigation_control_list": controls_for_mitigation,
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


def _catalog_entry(entry: RiskEntry) -> dict:
    """The catalog definition an accepted suggestion came from, or {}."""
    if not entry.source_catalog_id:
        return {}
    return next(
        (
            e
            for e in entry.source_catalog.content.get("entries", [])
            if e.get("id") == entry.source_catalog_entry_id
        ),
        {},
    )


def _missing_cyber_cause(entry: RiskEntry) -> bool:
    """A catalog hazard listing a cyberattack cause that isn't recorded yet;
    accepting the suggestion can't create it, since it must name a threat."""
    if entry.entry_type != EntryType.HAZARD:
        return False
    return (
        CauseType.CYBERATTACK in _catalog_entry(entry).get("causes", [])
        and not entry.causes.filter(cause_type=CauseType.CYBERATTACK).exists()
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
            "crumbs": breadcrumbs(
                configuration=configuration,
                trail=[("Risk register", reverse("risk:register", args=[configuration.pk]))]
                + (
                    [("Add entry", None)]
                    if is_new
                    else [
                        (
                            entry.label,
                            reverse("risk:entry_detail", args=[configuration.pk, entry.pk]),
                        ),
                        ("Edit", None),
                    ]
                ),
            ),
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
    allowed = {c["id"] for c in merged_categories(applicable_methods(entry, _methods()))}
    try:
        if consequence.impact_category not in allowed:
            raise ValidationError(
                {"impact_category": "Choose an impact category of this threat's risk methods."}
            )
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
        with transaction.atomic():
            _save_treatment(request, entry, method, treatment)
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "rating")
    django_messages.success(request, f"Treatment under {method.source} saved.")
    return _back(configuration, entry, "rating")


def _apply_mitigation_controls(request, entry):
    """Link the controls ticked in the treatment form, and create a new one if
    named, before the mitigation is checked (ADR 0033). A threat's picks
    replace its control links; a hazard's are set per cause. Raises
    ValidationError for a new control that doesn't validate."""
    product_controls = {c.pk: c for c in Control.objects.filter(product=entry.product)}

    def picked(field):
        return [
            product_controls[int(v)]
            for v in request.POST.getlist(field)
            if v.isdigit() and int(v) in product_controls
        ]

    if entry.entry_type == EntryType.THREAT:
        targets = {None: (entry.controls, picked("controls"))}
    else:
        targets = {
            cause.pk: (cause.controls, picked(f"cause_controls_{cause.pk}"))
            for cause in entry.causes.all()
        }
    name = request.POST.get("new_control_name", "").strip()
    if name:
        cause_id = request.POST.get("new_control_cause", "")
        key = (
            None
            if entry.entry_type == EntryType.THREAT
            else (int(cause_id) if cause_id.isdigit() else None)
        )
        if key not in targets:
            raise ValidationError("Choose the cause the new control addresses.")
        control = Control(
            product=entry.product,
            name=name,
            status=request.POST.get("new_control_status", ControlStatus.PLANNED),
        )
        control._history_user = request.user
        control.full_clean()
        control.save()
        targets[key][1].append(control)
    for manager, controls in targets.values():
        manager.set(controls)


def _save_treatment(request, entry, method, treatment):
    """Validate and save ``treatment``; raises ValidationError, so the caller's
    transaction also undoes any control links made for it."""
    if treatment.treatment_type == TreatmentType.MITIGATE and request.POST.get("controls_form"):
        _apply_mitigation_controls(request, entry)
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
    # A mitigation needs a plan: at least one control saying how.
    if mitigation_state(treatment) == mitigation.NO_CONTROLS:
        raise ValidationError(
            "Pick at least one control: it is the plan for how the risk is "
            + (
                "mitigated."
                if entry.entry_type == EntryType.THREAT
                else "mitigated, under the hazard cause it addresses."
            )
        )
    treatment.save()


@login_required
@require_POST
def control_link(request, pk, entry_pk):
    """Link an existing control, or create a new one and link it, to a threat
    or (with ``cause``) to one of a hazard's causes."""
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    target = _control_target(request, entry)
    if target is None:
        return _back(configuration, entry, "controls")
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
    target.add(control)
    django_messages.success(request, f"Control “{control.name}” linked.")
    return _back(configuration, entry, "controls")


def _control_target(request, entry):
    """The related manager a control is linked through: the threat's
    ``controls``, or a hazard cause's ``controls``. None (with a message) if
    neither applies."""
    if entry.entry_type == EntryType.THREAT:
        return entry.controls
    cause_id = request.POST.get("cause", "")
    if entry.entry_type == EntryType.HAZARD and cause_id.isdigit():
        cause = HazardCause.objects.filter(pk=int(cause_id), hazard=entry).first()
        if cause is not None:
            return cause.controls
    django_messages.error(request, "Controls link to a threat, or to one of a hazard's causes.")
    return None


@login_required
@require_POST
def control_unlink(request, pk, entry_pk, control_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    control = get_object_or_404(Control, pk=control_pk, product=entry.product)
    target = _control_target(request, entry)
    if target is None:
        return _back(configuration, entry, "controls")
    target.remove(control)
    django_messages.success(request, f"Control “{control.name}” unlinked.")
    return _back(configuration, entry, "controls")


@login_required
@require_POST
def cause_add(request, pk, entry_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    if entry.entry_type != EntryType.HAZARD:
        django_messages.error(request, "Only hazards have causes.")
        return _back(configuration, entry)
    threat_id = request.POST.get("threat", "")
    cause = HazardCause(
        hazard=entry,
        cause_type=request.POST.get("cause_type", ""),
        description=request.POST.get("description", "").strip(),
    )
    # Only a cyberattack names the responsible threat (HazardCause.clean()).
    if cause.cause_type == CauseType.CYBERATTACK and threat_id.isdigit():
        cause.threat = RiskEntry.objects.filter(
            pk=int(threat_id), product=entry.product, entry_type=EntryType.THREAT
        ).first()
    try:
        cause.full_clean()
    except ValidationError as exc:
        _flash_errors(request, exc)
        return _back(configuration, entry, "causes")
    cause.save()
    django_messages.success(request, f"Cause “{cause.get_cause_type_display()}” added.")
    return _back(configuration, entry, "causes")


@login_required
@require_POST
def cause_delete(request, pk, entry_pk, cause_pk):
    configuration, entry = _editable_entry(request, pk, entry_pk)
    if configuration is None:
        return entry
    get_object_or_404(HazardCause, pk=cause_pk, hazard=entry).delete()
    django_messages.success(request, "Cause removed; its controls are kept.")
    return _back(configuration, entry, "causes")


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
            "crumbs": breadcrumbs(
                configuration=configuration,
                trail=[
                    ("Risk register", reverse("risk:register", args=[configuration.pk])),
                    (entry.label, reverse("risk:entry_detail", args=[configuration.pk, entry.pk])),
                    ("Delete", None),
                ],
            ),
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


# --- Suggestion review --------------------------------------------------------------


def _suggestion_rows(configuration) -> list[dict]:
    return [
        {
            **s,
            "key": f"{s['catalog'].pk}:{s['entry_id']}",
            "type_label": EntryType(s["entry_type"]).label,
            "violates_label": s.get("violates", "").replace("_", " ").capitalize(),
            "cause_labels": [CauseType(c).label for c in s.get("causes", [])],
        }
        for s in pending_suggestions(configuration)
    ]


@login_required
def suggestions(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    return render(
        request,
        "risk/suggestions.html",
        {
            "crumbs": breadcrumbs(
                configuration=configuration,
                trail=[
                    ("Risk register", reverse("risk:register", args=[configuration.pk])),
                    ("Suggestions", None),
                ],
            ),
            "configuration": configuration,
            "product": product,
            "pending": _suggestion_rows(configuration),
            "dismissed": RiskEntry.objects.filter(
                product=product, suggestion_status=SuggestionStatus.DISMISSED
            )
            .select_related("source_catalog", "created_by")
            .order_by("label"),
            "assets": RiskEntry.objects.filter(product=product, entry_type=EntryType.ASSET)
            .exclude(suggestion_status=SuggestionStatus.DISMISSED)
            .order_by("label"),
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
        },
    )


def _pending_suggestion(request, configuration):
    """The pending suggestion a POST names, or None: only a suggestion this
    configuration's answers actually trigger, and that is still undecided."""
    catalog_id, _, entry_id = request.POST.get("suggestion", "").partition(":")
    for suggestion in pending_suggestions(configuration):
        if str(suggestion["catalog"].pk) == catalog_id and suggestion["entry_id"] == entry_id:
            return suggestion
    django_messages.error(request, "That suggestion is no longer pending.")
    return None


def _suggestion_editor(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to review suggestions.")
        return None, None
    return configuration, product


@login_required
@require_POST
def suggestion_accept(request, pk):
    configuration, product = _suggestion_editor(request, pk)
    if (
        configuration is None
        or (suggestion := _pending_suggestion(request, configuration)) is None
    ):
        return redirect("risk:suggestions", pk=pk)
    asset_id = request.POST.get("asset", "")
    asset = (
        RiskEntry.objects.filter(
            pk=int(asset_id), product=product, entry_type=EntryType.ASSET
        ).first()
        if asset_id.isdigit()
        else None
    )
    with transaction.atomic():
        entry = accept_suggestion(
            product, suggestion["catalog"], suggestion["entry_id"], actor=request.user
        )
        if asset is not None and entry.entry_type == EntryType.THREAT:
            entry.asset = asset
            entry.save(update_fields=["asset"])
        added = []
        if entry.entry_type == EntryType.THREAT and request.POST.get("add_controls"):
            for name in suggestion.get("suggested_controls", []):
                # Reuse a product control of the same name: one control can
                # mitigate several threats.
                control = Control.objects.filter(product=product, name=name).first()
                if control is None:
                    control = Control.objects.create(product=product, name=name)
                control.threats.add(entry)
                added.append(name)
    detail_url = reverse("risk:entry_detail", args=[configuration.pk, entry.pk])
    message = format_html('Accepted <a href="{}">{}</a>.', detail_url, entry.label)
    if added:
        message = format_html("{} Linked planned controls: {}.", message, ", ".join(added))
    django_messages.success(request, message)
    return redirect("risk:suggestions", pk=pk)


@login_required
@require_POST
def suggestion_dismiss(request, pk):
    configuration, product = _suggestion_editor(request, pk)
    if (
        configuration is None
        or (suggestion := _pending_suggestion(request, configuration)) is None
    ):
        return redirect("risk:suggestions", pk=pk)
    reason = request.POST.get("reason", "").strip()
    if not reason:
        django_messages.error(request, "Give a reason for dismissing the suggestion.")
        return redirect("risk:suggestions", pk=pk)
    dismiss_suggestion(
        product, suggestion["catalog"], suggestion["entry_id"], reason=reason, actor=request.user
    )
    django_messages.success(request, f"Dismissed “{suggestion['label']}”.")
    return redirect("risk:suggestions", pk=pk)


@login_required
@require_POST
def suggestion_restore(request, pk, entry_pk):
    """Accept a previously dismissed suggestion after all."""
    configuration, product = _suggestion_editor(request, pk)
    if configuration is None:
        return redirect("risk:suggestions", pk=pk)
    entry = get_object_or_404(
        RiskEntry, pk=entry_pk, product=product, suggestion_status=SuggestionStatus.DISMISSED
    )
    entry.suggestion_status = SuggestionStatus.ACCEPTED
    entry.dismissal_reason = ""
    entry.save(update_fields=["suggestion_status", "dismissal_reason", "updated_at"])
    detail_url = reverse("risk:entry_detail", args=[configuration.pk, entry.pk])
    django_messages.success(
        request, format_html('Accepted <a href="{}">{}</a> after all.', detail_url, entry.label)
    )
    return redirect("risk:suggestions", pk=pk)


@login_required
@require_POST
def approve(request, pk):
    """Approve the configuration's register view: a new RiskAssessment with a
    frozen snapshot (apps.risk.approval). Re-approving after changes starts a
    new one; earlier snapshots stay as history."""
    configuration = get_object_or_404(Configuration, pk=pk)
    product = configuration.hardware_revision.hardware_variant.product
    if not has_role(request.user, Role.APPROVER, product=product):
        django_messages.error(request, "You need the approver role to approve the risk register.")
        return redirect(reverse("risk:register", args=[pk]) + "#approval")
    if not register_for_configuration(configuration):
        django_messages.error(request, "The risk register is empty; there is nothing to approve.")
        return redirect(reverse("risk:register", args=[pk]) + "#approval")
    current = latest_risk_assessment(configuration)
    if current and current.status == RiskAssessmentStatus.APPROVED and not current.stale:
        django_messages.info(request, "The risk register is already approved and up to date.")
        return redirect(reverse("risk:register", args=[pk]) + "#approval")
    risk_assessment = (
        current
        if current and current.status != RiskAssessmentStatus.APPROVED
        else RiskAssessment.objects.create(configuration=configuration)
    )
    try:
        approve_risk_assessment(risk_assessment, actor=request.user)
        django_messages.success(request, "Risk register approved.")
    except RiskAssessmentError as exc:
        django_messages.error(request, str(exc))
    return redirect(reverse("risk:register", args=[pk]) + "#approval")
