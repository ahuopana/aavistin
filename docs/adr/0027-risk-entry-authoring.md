# 27. Adding and editing risk register entries in the app

Status: Accepted

## Context

The risk register model (ADR 0005) was complete, but the only way to create or change an entry was Django admin; the register and entry pages were read-only. This is the first authoring slice. Rating, treatment, controls, deltas, suggestion review and approval follow in later slices.

## Decisions

- **A dedicated form page, not an inline `<details>` form.** An entry has several fields that depend on its type, and the products pages' flash-and-redirect pattern (ADR 0010) loses what was typed when validation fails. The form re-renders with the input kept and the errors as messages; everything else follows ADR 0010 (function views, inline `has_role`, `full_clean`, plain HTML forms, no `forms.py`).
- **Editor role on the product**, checked with `has_role(..., product=...)` so grants at organisation, family or product level all count. The register's own `can_edit` now uses the same check.
- **Entry type is fixed after creation.** Ratings, consequences, causes and controls depend on it; changing type means adding a new entry.
- **Scope is one choice** of baseline, a HW variant, a SW release or a SW option of the same product, matching `RiskEntry.clean()`'s "at most one scope". Creating deltas (`base_entry`) is not in this slice, and an entry that is a delta or has deltas keeps its scope, so the baseline/delta pairing in `apps.risk.resolution` can't be broken from the form.
- **One violated property per threat; the form can create several at once.** One attack often breaks more than one property (remote code execution can hit confidentiality, integrity and availability). The model keeps one property per threat, because rating and treatment are per property: a control usually mitigates one property (encryption protects confidentiality, signing protects integrity), likelihood differs (reading is usually easier than undetected modification), and a threat's default severity is the asset's rating for that property. Common threat-analysis practice (e.g. the TARA in ISO/SAE 21434) also pairs one threat scenario with one asset and one property. To avoid triple entry, a new threat may tick several properties: one entry is created per property, all-or-nothing, labelled "Label (Property)". Editing changes one entry, so it keeps a single property. A parent "attack" grouping property-specific threats under one shared likelihood was considered and deferred until repeated likelihoods prove to be a real problem in use.
- **"Violates" choices come from the approved methods' `properties`**, in method order, falling back to CIA when no method is approved, and are validated on save. An existing threat keeps its property selectable on edit even if that method is no longer approved. The application doesn't hard-code which properties exist.
- **Entries are created as `custom`** (not suggested) with `created_by` and the history user set to the editor.

## Consequences

- Entries can't be deleted in the app yet; that comes with the controls/treatment slice, since deleting needs rules for linked ratings, consequences and controls.
- Threats can be saved without an asset (the model allows it) so a threat can be recorded before its asset exists.
