"""Suggests register entries from catalog triggers, against an
assessment's resolved answers and findings.

See docs/architecture.md, "Suggestions from applicability": "Wi-Fi
present -> wireless threats", etc. A suggestion is only a proposal — the
user accepts it (creating an accepted RiskEntry) or dismisses it with a
reason (creating a dismissed one, for the audit trail); either way it
stops being suggested again.
"""

from apps.assessments.evaluation import evaluate_configuration
from apps.packages.catalog_engine import triggered_entries
from apps.packages.models import PackageKind, PackageStatus, RequirementPackage

from .models import CauseType, EntryType, HazardCause, RiskEntry, SuggestionStatus

# Catalog-declared hazard causes create a HazardCause row automatically,
# except cyberattack: that type requires linking the specific threat
# entry responsible (see HazardCause.clean()), which a catalog trigger
# can't establish on its own — it's a manual follow-up.
AUTO_LINKABLE_CAUSES = {
    CauseType.HARDWARE_FAILURE,
    CauseType.SOFTWARE_FAULT,
    CauseType.FORESEEABLE_MISUSE,
}


def suggestion_context(configuration) -> dict:
    """Answers + findings, flattened into one {id: truthy} dict for triggers."""
    evaluation = evaluate_configuration(configuration)
    context = {qid: ra["value"] for qid, ra in evaluation["resolved_answers"].items()}
    for finding in evaluation["findings"]:
        context[finding["id"]] = True
    return context


def _find_catalog_entry(catalog, entry_id: str) -> dict:
    for entry in catalog.content.get("entries", []):
        if entry["id"] == entry_id:
            return entry
    raise KeyError(f"'{entry_id}' not found in catalog {catalog.source}@{catalog.version}")


def pending_suggestions(configuration) -> list[dict]:
    """Catalog-triggered entries not yet accepted or dismissed for this product."""
    product = configuration.hardware_revision.hardware_variant.product
    context = suggestion_context(configuration)

    already_decided = set(
        RiskEntry.objects.filter(product=product, source_catalog__isnull=False).values_list(
            "source_catalog_id", "source_catalog_entry_id"
        )
    )

    suggestions = []
    catalogs = RequirementPackage.objects.filter(
        kind=PackageKind.CATALOG, status=PackageStatus.APPROVED
    )
    for catalog in catalogs:
        for entry_id in triggered_entries(catalog.content, context):
            if (catalog.id, entry_id) in already_decided:
                continue
            suggestions.append(
                {
                    "catalog": catalog,
                    "entry_id": entry_id,
                    **_find_catalog_entry(catalog, entry_id),
                }
            )
    return suggestions


def _create_entry_from_catalog(product, catalog, entry_id, *, status, actor=None, reason=""):
    entry_def = _find_catalog_entry(catalog, entry_id)
    entry = RiskEntry(
        product=product,
        entry_type=entry_def["entry_type"],
        label=entry_def["label"],
        description=entry_def.get("description", ""),
        violates=entry_def.get("violates", ""),
        source_catalog=catalog,
        source_catalog_entry_id=entry_id,
        suggestion_status=status,
        dismissal_reason=reason,
        created_by=actor,
    )
    entry.full_clean()
    entry.save()

    if entry.entry_type == EntryType.HAZARD:
        for cause_type in entry_def.get("causes", []):
            if cause_type in AUTO_LINKABLE_CAUSES:
                HazardCause.objects.create(hazard=entry, cause_type=cause_type)

    return entry


def accept_suggestion(product, catalog, entry_id, *, actor=None) -> RiskEntry:
    return _create_entry_from_catalog(
        product, catalog, entry_id, status=SuggestionStatus.ACCEPTED, actor=actor
    )


def dismiss_suggestion(product, catalog, entry_id, *, reason: str, actor=None) -> RiskEntry:
    if not reason:
        raise ValueError("Dismissing a suggestion requires a reason.")
    return _create_entry_from_catalog(
        product, catalog, entry_id, status=SuggestionStatus.DISMISSED, actor=actor, reason=reason
    )
