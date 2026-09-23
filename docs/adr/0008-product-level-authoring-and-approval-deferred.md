# 8. Product-level authoring and approval: scope, and the admin-only boundary (deferred)

Status: Accepted (scope only — implementation deferred)

## Context

`apps/products` has no application-level UI: `views.py` is empty and
there is no `urls.py`. The only way to create or edit a `Product`, or
anything beneath it (`HardwareVariant`, `HardwareRevision`,
`SoftwareRelease`, `SoftwareOption`, `Configuration`), is Django admin's
`ProductAdmin` and friends — vanilla `admin.ModelAdmin`s with no
permission overrides.

Django admin authorization is governed entirely by `is_staff` plus
Django's built-in `auth.Permission`/`is_superuser` system. That is
completely disconnected from this project's own authorization model:
`RoleAssignment` (`apps/orgs/models.py`) and `has_role()`
(`apps/orgs/services.py`), which `docs/architecture.md`'s "Organisations
and roles" table already documents as covering exactly this — "Editor:
Answer questions, create releases and configurations." A user holding an
Editor `RoleAssignment` on a product, product family or organisation
today has no way to actually exercise that role: they aren't Django
staff, so `/admin/` refuses them outright, and even a staff user's
`RoleAssignment` grants have no bearing on the Django `Permission`
objects admin actually checks.

This was surfaced by hand-testing PR #1 outside admin mode: an
otherwise-authorized user could not modify a product. It's a real gap
between the documented design and what's built, not a bug in either.

## Decision

Scope, agreed for a future PR (not implemented here):

- **Product and everything beneath it** — `Product`, `HardwareVariant`,
  `HardwareRevision`, `SoftwareRelease`, `SoftwareOption`,
  `Configuration` — gets a non-admin authoring surface (Django templates
  + HTMX, per the project's stack), gated by `apps.orgs.services.has_role()`
  rather than Django's `is_staff`/`Permission` system. Add and modify
  actions at this level never require Django admin access.
- These entities gain their own **approval** concept, separate from
  assessment-snapshot approval (`apps/assessments/services.py`,
  `apps/risk/approval.py`), which stays as-is. Once an entity is
  approved, it cannot be deleted. Unapproved entities may be deleted
  freely by a user holding the appropriate role. Who may approve, and
  whether an approved entity can still be modified, are left for the
  implementing PR — not decided here.
- **`ProductFamily`, `Organisation`, `Group`, `RequirementPackage`**
  (all three `PackageKind`s: requirement, method, catalog) **and `User`**
  records stay Django-admin-only. This is deliberate, not a gap to close
  later — the "Content curator: Import and manage requirement sources"
  and "Organisation admin: Manage members, role assignments and
  policies" rows already point at admin/management-command-driven
  workflows for these, and nothing here changes that.

This ADR records the scope and boundary so the implementing PR builds
the right-sized thing — matching what "Organisations and roles" already
promises for Editor — instead of re-deriving it. No code changes land
with this ADR; today's actual behavior (Product-level editing is
Django-admin-only) is an accepted, known gap until that PR lands.

## Consequences

- A future PR needs `apps/products/views.py` + `urls.py` + templates,
  permission checks via `has_role()` (mirroring the pattern already used
  read-only in `apps/orgs/views.py`), and an approval-state field (or
  similar) on the relevant models with delete protection once approved.
- Django admin remains the *only* authoring path for `ProductFamily`,
  `Organisation`, `Group`, packages and users — no change needed there,
  now or later, unless a future decision revisits it explicitly.
- Until implemented, `ProductAdmin` and friends keep working exactly as
  they do today (staff-only); this ADR does not touch `apps/products/admin.py`.
