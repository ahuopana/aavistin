# 5. One RiskEntry model for asset/threat/hazard, not three tables

Status: Accepted

## Context

`docs/architecture.md`, "Risk register", describes three typed entries
(asset, threat, hazard) that share a lot of mechanics — scoping to a HW
variant/SW release/option, configuration-view deltas, provenance from a
catalog suggestion — but differ in what they're rated on: an asset gets
a per-CIA-property severity, a hazard gets a directly-rated
severity+likelihood, a threat's severity is derived from its worst
consequence and only its likelihood is stored.

## Decision

`apps.risk.models.RiskEntry` is one table with an `entry_type` column
(asset/threat/hazard), carrying the shared fields (scoping, delta,
provenance, suggestion status). Type-specific data lives in separate
related tables: `AssetRating` (per property, per method), `Rating`
(likelihood always, severity only for hazards — threats derive theirs),
`ThreatConsequence` (per impact category, optionally linked to a hazard
entry) and `HazardCause` (per cause type, optionally linked to a threat
entry for the cyberattack cause). `RiskEntry.clean()` enforces the
type-specific rules that a shared table can't express as column
constraints (a threat must declare what it `violates`, a hazard can't
target an `asset`, and so on).

Scoping reuses the pattern from `Answer` and `RoleAssignment` (nullable
FK per level), but relaxed: at most one of `scope_hardware_variant` /
`scope_software_release` / `scope_software_option` may be set, and *zero*
set is valid and means "baseline" — unlike those two models, where a
scope is always required. A scoped entry additionally carrying
`base_entry` is a delta that replaces that baseline entry for matching
configurations; `apps/risk/resolution.py` resolves the view.

## Consequences

- Adding a field common to all three types (e.g. provenance, audit
  history via `HistoricalRecords`) is one migration, not three.
- Cross-type queries (a product's whole register) are a single
  `RiskEntry.objects.filter(product=...)`, not a union of three tables.
- The trade-off is a table with several nullable, type-conditional
  columns (`asset`, `violates`) validated only in Python, not by the
  database. Given `clean()` is always called from the service layer
  (`apps/risk/suggestions.py`) and the admin (`ModelAdmin.save_model`
  calls `full_clean()`), this is the same trade already accepted for
  `Answer`'s exactly-one-owner shape in Milestone 5.

## Also in this milestone: cross-method consistency rule 3 is manual

`docs/architecture.md` lists a third cross-method rule: "A control on the
threat (e.g. secure boot) may lower the likelihood of the hazard's cyber
cause, confirmed by the reviewer." `apps/risk/consistency.py` implements
rules 1 (can't accept a threat while its linked hazard is unacceptable)
and 2 (severity-mapping floor) as pure functions returning issues to
show the user. Rule 3 describes a reviewer action (editing the hazard
cause's likelihood after adding a control), not a computation to run
automatically — there's nothing to derive without inventing a specific
"how much does this control lower it by" formula the architecture doc
doesn't specify. `Control` already links to both `RiskEntry` (threats)
and `HazardCause`, so a reviewer can make that edit; automating a
suggested delta is left for when a concrete formula exists.

## Also: catalog-suggested cyberattack hazard causes aren't auto-linked

`HazardCause.clean()` requires a cyberattack cause to name the
responsible threat entry. When `apps/risk/suggestions.py` accepts a
catalog-suggested hazard whose `causes` list includes `cyberattack`, it
does not create that `HazardCause` row automatically — the catalog entry
only names a cause *type*, not which specific threat entry in *this*
product's register is responsible (that threat may not have been
accepted yet, or may not exist in the catalog at all). Non-cyberattack
causes (hardware_failure, software_fault, foreseeable_misuse) are
created automatically since they need no such link. Linking a cyberattack
cause to its threat is left as a manual step in the register.
