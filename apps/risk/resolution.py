"""Resolves a Configuration's risk register view: baseline entries plus
any matching deltas, deltas replacing the baseline entry they override.

See docs/architecture.md, "Risk register" -> "Product baseline and
configuration deltas".
"""

from .models import RiskEntry, SuggestionStatus


def register_for_configuration(configuration) -> list[RiskEntry]:
    product = configuration.hardware_revision.hardware_variant.product
    hardware_variant_id = configuration.hardware_revision.hardware_variant_id
    software_release_id = configuration.software_release_id
    option_ids = set(configuration.software_options.values_list("id", flat=True))

    entries = list(
        RiskEntry.objects.filter(product=product)
        .exclude(suggestion_status=SuggestionStatus.DISMISSED)
        .select_related(
            "scope_hardware_variant", "scope_software_release", "scope_software_option"
        )
    )

    view: dict[int, RiskEntry] = {e.id: e for e in entries if e.is_baseline}

    for entry in entries:
        if entry.is_baseline:
            continue
        if (
            entry.scope_hardware_variant_id
            and entry.scope_hardware_variant_id != hardware_variant_id
        ):
            continue
        if (
            entry.scope_software_release_id
            and entry.scope_software_release_id != software_release_id
        ):
            continue
        if entry.scope_software_option_id and entry.scope_software_option_id not in option_ids:
            continue
        # Matches this configuration: it's either a delta replacing its
        # base entry, or a standalone configuration-scoped addition.
        if entry.base_entry_id and entry.base_entry_id in view:
            del view[entry.base_entry_id]
        view[entry.id] = entry

    return list(view.values())
