# 19. When a requirement applies: conditions, dates, roles

Status: Accepted

## Context

Requirements were filtered only by classification (`applies_to_classes`). Roles were tags nobody read, and the only dates were package-level `dates_of_application`, which evaluation ignored. The CRA needs all three: Art. 14 reporting has applied since 11 September 2026 to every in-scope product; the essential requirements apply to products placed from 11 December 2027; Part II ends with the support period; importers, distributors, authorised representatives and open-source stewards each have their own obligations. The plan (`docs/plans/eu-cra-full.md`, 4.1.1) separates dates compared with the **assessment date** from dates compared with the **placement date**.

## Decision

A requirement may declare:

- **`applies_when`**: an expression over answers (and the `class__` variables, as for routes and findings). This is where placement-based rules live, as comparisons on placement-date questions (ADR 0018). The engine never knows which question holds a placement date, so no regulation is hard-coded.
- **`applies_from` / `applies_until`**: ISO dates compared with the assessment date (the evaluation's `as_of`, today by default), for duties that follow the calendar whatever the product's age. `until` is exclusive.
- **`roles`**, now read. A package may declare **`role`**: an expression that yields the economic operator role for the configuration, e.g. "manufacturer if an importer places it under its own name, else the answered role". A requirement applies when the role is unknown (unanswered: nothing is hidden) or listed in `roles`. Roles add `authorised_representative` and `steward`.

Evaluation reports, per package: `requirements` (in force), `upcoming_requirements` (`applies_from` after `as_of`), `ended_requirements` (`applies_until` on or before `as_of`) and `role`. The assessment page shows upcoming and ended requirements with their dates rather than hiding them.

**Staleness** also compares the in-force requirements, so an approved assessment is flagged when a date passes (the periodic staleness job, ADR 0007) or an answer changes them.

**Fixtures** may set `as_of` and expect `classifications`, `assessment_routes` and `requirements`. A fixture that expects requirements must set `as_of`, so it does not change meaning over time (lint error otherwise).

## Consequences

- Package-level `dates_of_application` stay informational; date logic lives on requirements, where it differs within one law.
- The linter checks `applies_when` and `role` expressions like other rules, and the date formats and order.
- A package without `role` behaves as before (no role filtering).
