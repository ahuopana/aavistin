"""Current-status metrics over a risk register: completeness, exposure,
treatment quality, and whether the approved view is still current.

Read-only and method-neutral: levels belong to a method, but every method
maps its levels to the same three acceptance classes (``must_treat``,
``justify``, ``accept``), so entries are aggregated by class, never by
adding severities across methods (docs/architecture.md, "Cross-method
rules"). There is deliberately no composite score. Definitions are in
docs/plans/risk-metrics.md and docs/userguide/05-risk-assessment.md.

An entry's *inherent* position is its rating before treatment. Its
*residual* (effective) position is the treatment's residual rating when
that can be relied on, and its inherent position otherwise: no treatment,
a treatment without a residual rating, or a mitigation whose controls are
not yet in place (apps.risk.mitigation).
"""

from django.utils import timezone

from apps.packages.method_engine import evaluate_matrix
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage
from apps.products.models import Configuration

from .consistency import check_threat_hazard_consistency
from .mitigation import IN_PLACE, NO_CONTROLS, PLANNED, mitigation_state, treatment_counts
from .models import (
    Control,
    ControlStatus,
    EntryType,
    RiskAssessmentStatus,
    RiskEntry,
    SuggestionStatus,
    TreatmentType,
)
from .rating import evaluate_residual_rating
from .resolution import register_for_configuration

# Worst first. Rank 0 is "not rated".
CLASSES = ("must_treat", "justify", "accept")
RANK = {"must_treat": 3, "justify": 2, "accept": 1}
CLASS_LABELS = {
    "must_treat": "must treat",
    "justify": "justify",
    "accept": "accept",
    "unrated": "unrated",
}
ACCEPTABLE = ("accept", "justify")
TOP_LIMIT = 5

RATEABLE = (EntryType.THREAT, EntryType.HAZARD)


def _rank(acceptance) -> int:
    return RANK.get(acceptance, 0)


def _worst(acceptances) -> str | None:
    best = max((_rank(a) for a in acceptances), default=0)
    return next((c for c in CLASSES if RANK[c] == best), None) if best else None


def _load(entries) -> list[RiskEntry]:
    """The same entries with everything the metrics read prefetched."""
    ids = [e.pk for e in entries]
    return list(
        RiskEntry.objects.filter(pk__in=ids)
        .select_related("asset")
        .prefetch_related(
            "ratings__method",
            "treatments__method",
            "consequences",
            "controls",
            "causes__controls",
            "asset_ratings",
        )
        .order_by("entry_type", "label", "pk")
    )


def _entry_controls(entry) -> list[Control]:
    """Controls that mitigate the entry (as apps.risk.mitigation, but from
    prefetched data)."""
    if entry.entry_type == EntryType.THREAT:
        return list(entry.controls.all())
    found = {}
    for cause in entry.causes.all():
        for control in cause.controls.all():
            found[control.pk] = control
    return list(found.values())


def _severity(entry, rating) -> int | None:
    if entry.entry_type == EntryType.HAZARD:
        return rating.severity
    severities = [c.severity for c in entry.consequences.all()]
    return max(severities) if severities else None


def _position(method, severity, likelihood) -> dict:
    result = evaluate_matrix(method.content, severity, likelihood)
    return {
        "severity": severity,
        "likelihood": likelihood,
        "level": result["level"],
        "acceptance": result["acceptance"],
    }


def _entry_state(entry) -> dict:
    """Per-method inherent and effective residual positions for a threat or
    hazard, plus its overall classes."""
    controls = _entry_controls(entry)
    treatments = {t.method_id: t for t in entry.treatments.all()}
    methods = []
    for rating in entry.ratings.all():
        severity = _severity(entry, rating)
        inherent = (
            _position(rating.method, severity, rating.likelihood) if severity is not None else None
        )
        treatment = treatments.get(rating.method_id)
        residual = inherent
        state = "untreated"
        if inherent is not None and treatment is not None:
            state = "no_residual"
            if (
                treatment.residual_severity is not None
                and treatment.residual_likelihood is not None
            ):
                state = "relied_on"
                if treatment_counts(treatment, controls):
                    residual = _position(
                        rating.method, treatment.residual_severity, treatment.residual_likelihood
                    )
                else:
                    state = "not_in_place"
        methods.append(
            {
                "method": rating.method,
                "inherent": inherent,
                "residual": residual,
                "treatment": treatment,
                "state": state,
            }
        )
    inherent_class = _worst(m["inherent"]["acceptance"] for m in methods if m["inherent"])
    residual_class = _worst(m["residual"]["acceptance"] for m in methods if m["residual"])
    return {
        "entry": entry,
        "controls": controls,
        "methods": methods,
        "inherent_class": inherent_class,
        "residual_class": residual_class,
        "acceptable": _acceptable(entry, controls),
    }


def _acceptable(entry, controls) -> bool:
    """The existing "risk acceptable" rule: the entry has treatments and every
    one has an acceptable residual that can be relied on."""
    treatments = list(entry.treatments.all())
    return bool(treatments) and all(
        evaluate_residual_rating(t)["acceptance"] in ACCEPTABLE and treatment_counts(t, controls)
        for t in treatments
    )


def _states(entries) -> list[dict]:
    return [_entry_state(e) for e in _load(entries) if e.entry_type in RATEABLE]


def _class_counts(states, key) -> dict:
    counts = {c: 0 for c in CLASSES}
    counts["unrated"] = 0
    for s in states:
        counts[s[key] or "unrated"] += 1
    return counts


def _segments(counts) -> list[dict]:
    """Bar segments for a class count dict, worst first, empty ones left out."""
    glyphs = {"must_treat": "\u2715", "justify": "!", "accept": "\u2713", "unrated": "\u2013"}
    return [
        {"key": key, "label": CLASS_LABELS[key], "glyph": glyphs[key], "count": counts[key]}
        for key in (*CLASSES, "unrated")
        if counts[key]
    ]


def _heatmaps(states) -> list[dict]:
    """One grid per method that rates at least one entry: severity rows (high
    at the top) by likelihood columns, with the entries at each cell before
    and after treatment."""
    methods = {}
    for s in states:
        for m in s["methods"]:
            methods[m["method"].pk] = m["method"]
    grids = []
    for method in sorted(methods.values(), key=lambda m: m.source):
        sev_lo, sev_hi = method.content["severity"]["scale"]
        lik_lo, lik_hi = method.content["likelihood"]["scale"]
        cells = {}
        for s in states:
            for m in s["methods"]:
                if m["method"].pk != method.pk or m["inherent"] is None:
                    continue
                for phase in ("inherent", "residual"):
                    pos = m[phase]
                    cell = cells.setdefault((pos["severity"], pos["likelihood"]), {})
                    cell.setdefault(phase, []).append(s["entry"])
        sev_labels = method.content["severity"].get("labels", [])
        lik_labels = method.content["likelihood"].get("labels", [])
        rows = []
        for sev in range(sev_hi, sev_lo - 1, -1):
            row = []
            for lik in range(lik_lo, lik_hi + 1):
                pos = _position(method, sev, lik)
                cell = cells.get((sev, lik), {})
                row.append(
                    {
                        **pos,
                        "inherent": cell.get("inherent", []),
                        "residual": cell.get("residual", []),
                    }
                )
            rows.append(
                {
                    "severity": sev,
                    "label": sev_labels[sev - sev_lo] if sev_labels else "",
                    "cells": row,
                }
            )
        grids.append(
            {
                "method": method,
                "rows": rows,
                "likelihoods": [
                    {"value": v, "label": lik_labels[v - lik_lo] if lik_labels else ""}
                    for v in range(lik_lo, lik_hi + 1)
                ],
            }
        )
    return grids


def _top_open(states) -> list[dict]:
    """The entries most in need of attention: still above ``accept`` after
    treatment, worst class first, then by the severity and likelihood of the
    rating that drives the class."""
    items = []
    for s in states:
        cls = s["residual_class"]
        if cls not in ("must_treat", "justify"):
            continue
        drivers = [m for m in s["methods"] if m["residual"] and m["residual"]["acceptance"] == cls]
        driver = max(
            drivers, key=lambda m: (m["residual"]["severity"], m["residual"]["likelihood"])
        )
        items.append(
            {
                "entry": s["entry"],
                "class": cls,
                "method": driver["method"],
                "severity": driver["residual"]["severity"],
                "likelihood": driver["residual"]["likelihood"],
                "level": driver["residual"]["level"],
                "state": driver["state"],
            }
        )
    items.sort(
        key=lambda i: (-RANK[i["class"]], -i["severity"], -i["likelihood"], i["entry"].label)
    )
    return items[:TOP_LIMIT]


def _treatment_metrics(states) -> dict:
    mix = {t.value: 0 for t in TreatmentType}
    mitigation = {NO_CONTROLS: 0, PLANNED: 0, IN_PLACE: 0}
    missing_justification = 0
    for s in states:
        for m in s["methods"]:
            treatment = m["treatment"]
            if treatment is None:
                continue
            mix[treatment.treatment_type] += 1
            if treatment.treatment_type == TreatmentType.MITIGATE:
                mitigation[mitigation_state(treatment, s["controls"])] += 1
            residual_acceptance = evaluate_residual_rating(treatment)["acceptance"]
            needs_justification = (
                treatment.treatment_type != TreatmentType.MITIGATE
                or residual_acceptance not in (None, "accept")
            )
            if needs_justification and not treatment.justification.strip():
                missing_justification += 1
    return {
        "mix": mix,
        "mitigation": mitigation,
        "mitigate_total": sum(mitigation.values()),
        "missing_justification": missing_justification,
    }


def _control_metrics(entries, product, *, include_unlinked: bool) -> dict:
    """Controls linked to these entries (all of the product's controls when
    ``include_unlinked``, which adds the ones linked to nothing)."""
    entry_ids = {e.pk for e in entries}
    controls = Control.objects.filter(product=product).prefetch_related(
        "threats", "hazard_causes", "evidence_links__evidence__superseded_by"
    )
    by_status = {s.value: 0 for s in ControlStatus}
    unlinked = verified_without_evidence = total = 0
    for control in controls:
        linked_threats = {t.pk for t in control.threats.all()}
        linked_hazards = {c.hazard_id for c in control.hazard_causes.all()}
        is_unlinked = not linked_threats and not linked_hazards
        in_view = bool((linked_threats | linked_hazards) & entry_ids)
        if not (in_view or (include_unlinked and is_unlinked)):
            continue
        total += 1
        by_status[control.status] += 1
        unlinked += is_unlinked
        if control.status == ControlStatus.VERIFIED and not any(
            not (link.evidence.is_expired or link.evidence.is_superseded)
            for link in control.evidence_links.all()
        ):
            verified_without_evidence += 1
    return {
        "total": total,
        "by_status": by_status,
        "unlinked": unlinked,
        "verified_without_evidence": verified_without_evidence,
    }


def _completeness(entries, states) -> dict:
    loaded = {e.pk: e for e in _load(entries)}
    assets = [e for e in loaded.values() if e.entry_type == EntryType.ASSET]
    threats = [e for s in states if (e := s["entry"]).entry_type == EntryType.THREAT]
    unrated = sum(1 for s in states if not s["methods"])
    incomplete = sum(1 for s in states if s["methods"] and s["inherent_class"] is None)
    rated = sum(1 for s in states if s["inherent_class"] is not None)
    treated = sum(1 for s in states if s["inherent_class"] is not None and _has_treatment(s))
    return {
        "rateable": len(states),
        "rated": rated,
        "unrated": unrated,
        "incomplete": incomplete,
        "treated": treated,
        "untreated": rated - treated,
        "assets": len(assets),
        "assets_unrated": sum(1 for a in assets if not a.asset_ratings.all()),
        "threats_without_consequence": sum(1 for t in threats if not t.consequences.all()),
    }


def _has_treatment(state) -> bool:
    return any(m["treatment"] is not None for m in state["methods"])


def _exposure(states) -> dict:
    inherent = _class_counts(states, "inherent_class")
    residual = _class_counts(states, "residual_class")
    reduced = sum(
        1
        for s in states
        if s["inherent_class"] and _rank(s["residual_class"]) < _rank(s["inherent_class"])
    )
    return {
        "inherent": inherent,
        "residual": residual,
        "open_must_treat": residual["must_treat"],
        "reduced": reduced,
        "inherent_segments": _segments(inherent),
        "residual_segments": _segments(residual),
        "by_type": {
            t.value: _class_counts(
                [s for s in states if s["entry"].entry_type == t], "residual_class"
            )
            for t in RATEABLE
        },
    }


def _consistency_issues(states) -> int:
    return sum(
        len(check_threat_hazard_consistency(s["entry"]))
        for s in states
        if s["entry"].entry_type == EntryType.THREAT
    )


def _compute(entries, product, *, include_unlinked_controls: bool) -> dict:
    entries = list(entries)
    states = _states(entries)
    counts = {t.value: sum(1 for e in entries if e.entry_type == t) for t in EntryType}
    return {
        "total": len(entries),
        "counts": counts,
        "completeness": _completeness(entries, states),
        "exposure": _exposure(states),
        "heatmaps": _heatmaps(states),
        "top": _top_open(states),
        "treatment": _treatment_metrics(states),
        "controls": _control_metrics(entries, product, include_unlinked=include_unlinked_controls),
        "consistency_issues": _consistency_issues(states),
        "acceptable": (sum(1 for s in states if s["acceptable"]), len(states)),
    }


def governance(configuration) -> dict:
    """Whether the configuration's latest risk assessment can be relied on."""
    latest = configuration.risk_assessments.order_by("-created_at").first()
    if latest is None:
        return {"status": "none", "label": "No risk assessment", "stale": False}
    result = {"status": latest.status, "stale": latest.stale}
    if latest.status != RiskAssessmentStatus.APPROVED:
        return {**result, "label": "Draft"}
    age = (timezone.now() - latest.approved_at).days if latest.approved_at else None
    behind = _versions_behind(latest.snapshot)
    label = "Approved, stale" if latest.stale else "Approved"
    return {
        **result,
        "label": label,
        "approved_at": latest.approved_at,
        "age_days": age,
        "versions_behind": behind,
        "assessment": latest,
    }


def _versions_behind(snapshot) -> list[dict]:
    """Method or catalog packages the snapshot used whose newest approved
    version is a different one."""
    behind = []
    for kind, key in ((PackageKind.METHOD, "methods"), (PackageKind.CATALOG, "catalogs")):
        for source, version in (snapshot or {}).get(key, []):
            newest = (
                RequirementPackage.objects.filter(
                    kind=kind, source=source, status=PackageStatus.APPROVED
                )
                .order_by("-approved_at", "-pk")
                .first()
            )
            if newest is not None and newest.version != version:
                behind.append({"source": source, "used": version, "latest": newest.version})
    return behind


def register_metrics(configuration) -> dict:
    """Metrics for one configuration's register view (baseline plus deltas)."""
    product = configuration.product
    metrics = _compute(
        register_for_configuration(configuration), product, include_unlinked_controls=False
    )
    metrics["governance"] = governance(configuration)
    return metrics


def _product_entries(product) -> list[RiskEntry]:
    """Every register entry that applies to at least one of the product's
    configurations, each once; the baseline when there are no configurations."""
    configurations = list(
        Configuration.objects.filter(software_release__product=product).select_related(
            "hardware_revision__hardware_variant", "software_release"
        )
    )
    if not configurations:
        return list(
            RiskEntry.objects.filter(
                product=product,
                scope_hardware_variant__isnull=True,
                scope_software_release__isnull=True,
                scope_software_option__isnull=True,
            ).exclude(suggestion_status=SuggestionStatus.DISMISSED)
        )
    union = {}
    for configuration in configurations:
        for entry in register_for_configuration(configuration):
            union[entry.pk] = entry
    return list(union.values())


def risk_summary(product) -> dict:
    """The small, cheap summary used for product lists: acceptable ratio,
    open must-treat entries and unrated entries, over every entry that applies
    to some configuration (a product-level roll-up, each entry once)."""
    states = _states(_product_entries(product))
    exposure = _exposure(states)
    return {
        "acceptable": sum(1 for s in states if s["acceptable"]),
        "total": len(states),
        "open_must_treat": exposure["residual"]["must_treat"],
        "unrated": sum(1 for s in states if not s["methods"]),
    }


def product_metrics(product) -> dict:
    """Roll-up for the product: exposure counts an entry once and as open if
    it is open (an entry's state does not depend on the configuration, only
    whether it applies does), plus one compact row per configuration."""
    metrics = _compute(_product_entries(product), product, include_unlinked_controls=True)
    rows = []
    configurations = Configuration.objects.filter(
        software_release__product=product
    ).select_related("hardware_revision__hardware_variant", "software_release")
    for configuration in configurations:
        per = register_metrics(configuration)
        rows.append(
            {
                "configuration": configuration,
                "total": per["total"],
                "rateable": per["completeness"]["rateable"],
                "unrated": per["completeness"]["unrated"],
                "untreated": per["completeness"]["untreated"],
                "exposure": per["exposure"],
                "acceptable": per["acceptable"],
                "governance": per["governance"],
            }
        )
    metrics["configurations"] = rows
    return metrics
