# 9. Product-level authoring implementation

Status: Accepted

## Context

ADR 0008 recorded the scope for closing the gap it found (Product and
below was Django-admin-only, despite "Organisations and roles" already
documenting Editor as able to "create releases and configurations") but
deliberately left several details to "the implementing PR": which role
approves, whether an approved entity can still be modified, and how a
brand-new deployment gets anyone past "logged in, nothing to do." This
ADR is that implementing PR's record of those decisions.

## Decision

- **Approve uses the `Approver` role**, not `Editor` — matching the
  existing precedent in `apps/assessments/views.py::assessment_approve`
  and `apps/risk`, where "add/modify" and "approve" are already split
  across `Editor` and `Approver`. Add/modify/delete (while unapproved)
  use `Editor`.
- **Modifying an approved entity stays allowed.** ADR 0008 only ever
  tied the approval concept to delete protection ("can be deleted unless
  approved" was the literal ask); nothing in that scope implies edits
  should freeze too, and freezing them would need its own review/re-
  approval workflow this ADR doesn't build. `apps/products/services.py`
  enforces exactly the delete rule (`delete_entity` raises
  `ApprovedEntityError` when `instance.is_approved`); `approve()` and
  every edit view leave `is_approved` untouched by a save.
- **Views and templates copy `apps/assessments/views.py`'s established
  shape exactly**: plain function views, `@login_required`, inline
  `has_role()` checks with a `django_messages.error` + redirect on
  failure, `full_clean()` + the Django messages framework for validation
  errors, plain HTML `<form>`s (no `forms.py`, no HTMX partials) — not a
  new style for this feature. `apps/products/services.py::product_of()`
  resolves the owning `Product` for any of the six models, so
  `entity_approve`/`entity_delete` in `apps/products/views.py` are two
  generic views (keyed by a `model_name` URL segment) rather than twelve
  near-identical ones.
- **`apps/products/services.py::editable_product_families()` /
  `editable_products()`** answer "what can this user create/edit,"
  reusing `RoleAssignment`'s existing hierarchy (organisation → family →
  product) the same way `apps.orgs.services.has_role()` already does for
  a single scope check — needed to populate the "create a product"
  entry point on `apps/orgs`'s existing `organisation_detail` page (the
  natural integration point, already listing product families).
- **Bootstrapping a fresh deployment**: `apps/orgs/management/commands/
  seed_dev_roles.py` (parallel to the existing `seed_dev_users`) creates
  one `Group` per `Role` choice, a Default Organisation / Default
  Family, and grants the seeded `aavistin` dev user both `Editor` and
  `Approver` there — one login can exercise the whole add → approve →
  (blocked) delete → delete flow. Wired into `docker-compose.yml`'s
  `web` command right after `seed_dev_users`. Same rules as that
  command: local development only, idempotent, never run against a
  non-dev database.

## Consequences

- `Product`, `HardwareVariant`, `HardwareRevision`, `SoftwareRelease`,
  `SoftwareOption`, `Configuration` each gain `is_approved`,
  `approved_at`, `approved_by` via a shared abstract `Approvable` mixin
  (`apps/products/models.py`) — one migration, not six near-duplicate
  field sets.
  `apps/products/admin.py` is untouched: Django admin keeps working
  exactly as before, independent of this new surface, per ADR 0008.
- A superuser or org admin with no `RoleAssignment` at all still can't
  use `/products/` for a product they hold no role on — `has_role()`
  doesn't special-case `is_superuser` (unlike `apps.products.services`'s
  own `editable_*` listing helpers, which do, for populating "what can I
  see" lists). This matches existing behavior for assessments/risk
  approval and isn't changed here.
- `ProductFamily`, `Organisation`, `Group` and `RequirementPackage`
  creation/editing remain Django-admin-only, exactly as ADR 0008
  decided — this PR doesn't revisit that boundary.
