# 12. Product status lifecycle, entity cloning, and portfolio-first navigation

Status: Accepted

## Context

A UX pass over `/products/<id>/` surfaced three gaps not covered by
`docs/architecture.md`:

1. **No product lifecycle.** `Product` (and everything beneath it) only had
   the `Approvable` mixin's `is_approved` — a delete-protection flag, per
   ADR 0008/0010, not a lifecycle. There was no way to represent "this
   product is done and CE marked" vs. "still being worked on" vs. "retired",
   and no soft delete — `entity_delete` hard-deleted a `Product` and
   everything under it the moment it wasn't yet approved.
2. **No cloning.** Starting a new hardware revision or software release
   meant re-typing every field from scratch.
3. **Organisation-first navigation.** "Organisations and roles" states
   organisation and product family "structure navigation in the
   master–detail layout" — but in practice this meant the only way to
   reach a product was Organisations → organisation → family → product,
   which the person actually using the tool found made organisation feel
   load-bearing when, day to day, they think in products, not org
   hierarchy.

This ADR was requested and decided directly by the product owner in
conversation, not inferred — including the exact status set and their
description of what each state means.

## Decision

**Product status** (`apps/products/models.py::ProductStatus`, a new
`status` field on `Product` only — not on `HardwareVariant` etc., which
keep only `is_approved`):

- `Draft` → `Approved` → `Closed` is the forward path. `Closed` means
  e.g. CE marked; nothing enforces that a risk assessment approval
  exists first (risk assessment, milestone 6, isn't built yet) — that
  link is future work, not decided here. Post-market monitoring can
  continue after closing.
- `Archived` and `Deleted` are side branches, both reversible. `Deleted`
  is a **soft** delete: hidden from the portfolio and dashboard, nothing
  removed from the database. This replaces hard delete for `Product`
  specifically; `entity_delete` still hard-deletes every other entity
  type exactly as ADR 0008/0010 specified.
- `is_approved`/`approved_at`/`approved_by` (the shared `Approvable`
  bits) are untouched in meaning — they still just mean "locked against
  hard deletion" per ADR 0008. Approving a still-`Draft` product also
  advances `status` to `Approved` (`services.py::approve_product`), so
  the two concepts move together at that one transition, but stay
  otherwise independent: `Closed`/`Archived`/`Deleted` are `status`-only
  moves, gated by `services.py`'s transition guards
  (`InvalidStatusTransition`) — Approve and Close need `Approver`;
  Archive, Restore and (soft) Delete need `Editor`, matching the
  Editor/Approver split ADR 0010 already established.
- `editable_products()` excludes `status=deleted` by default, so it
  disappears from the dashboard and portfolio without a query change at
  every call site.

**Cloning** (`hardware_variant`/`hardware_revision`/`software_release`/
`software_option`, `apps/products/services.py::clone_*`): copies the
entity's own fields (and, for a variant, its target markets) into a new
unapproved sibling, name/label/version suffixed " copy" / " copy N" for
uniqueness. Cloning a variant does not copy its revisions, and cloning a
release does not copy its options — each is its own clone action, kept
deliberately shallow rather than a deep-copy of the whole subtree.

**Portfolio navigation** (`apps/orgs/views.py::portfolio`,
`templates/orgs/portfolio.html`, `/orgs/portfolio/`): the primary nav
link ("Organisations" → "Portfolio") now leads to product families
flattened across every organisation the user can see, organisation shown
as a small caption per family rather than a level to click through.
This supersedes the navigation-structuring role "Organisations and
roles" gave organisation/family — organisation is still visible (and
still the real scope for roles, SoD policy, LDAP group mapping, all
unchanged), it's just no longer the primary navigation path. The old
`orgs:list`/`orgs:detail` views, templates and URLs are untouched and
still reachable directly; they're just no longer linked from the header.
`_redirect_to_owner()` (`apps/products/views.py`) now always returns to
`product_detail` (simplified — `product_of()` already resolves a
`Product` to itself), rather than bouncing a just-approved-or-deleted
product out to its organisation page, which mattered less before
`Product` delete was a hard delete and there was nothing to bounce back
to.

## Consequences

- `docs/architecture.md`'s "Organisations and roles" paragraph on
  navigation is now stale and should be updated when the design doc
  next touches that section — this ADR is the interim record.
- Any future risk-assessment-approval integration (milestone 6) that
  wants to gate `Closed` on an actual approved risk assessment extends
  `close_product()`'s guard; nothing here assumes that link exists yet.
- `HardwareVariant`, `HardwareRevision`, `SoftwareRelease`,
  `SoftwareOption`, `Configuration` still have no lifecycle beyond
  `is_approved` — only `Product` does. Extending status to those is a
  future decision, not implied by this one.
