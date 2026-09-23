# Project guide for Claude Code

Open-source compliance tool for product manufacturers: users assess which regulations (EU CRA, RED, LVD, GDPR and others) apply to their products, and later perform risk assessments. The full design is in `docs/ARCHITECTURE.md`; read it before starting any task and treat it as the source of truth.

## Working agreements

- Design work continues in parallel. When `docs/ARCHITECTURE.md` changes, re-read the changed sections before continuing. If code and design disagree, stop and ask rather than guessing.
- Record any decision not covered by the architecture doc as a short ADR in `docs/adr/NNNN-title.md`.
- Work milestone by milestone (below). Each milestone ends with passing tests, `ruff` clean and a short summary of what was built and what was deferred.

## Hard rules

- Define the custom user model (`AUTH_USER_MODEL`) before the first migration.
- PostgreSQL in development, CI and production (`docker compose` for local). Never rely on SQLite-only behaviour.
- Rule expressions in requirement packages are evaluated by a safe interpreter (JSONLogic or equivalent). Never `eval`/`exec`.
- Never commit text from standards (EN, IEC, ISO). Standards appear only as references, clause numbers and own summaries.
- Regulation content lives in packages under `packages/`, validated by the JSON Schema in `schemas/`. Application code must not hard-code any regulation's scope or requirements.
- Rendered Markdown is always sanitized with `nh3`.
- Configuration comes from environment variables; no secrets in the repository.

## Tooling

- `uv` for dependencies, `ruff` for lint and format, `pytest` + `pytest-django` for tests.
- Django templates + HTMX + Alpine.js; no SPA, no Node build unless an ADR justifies it.
- Default to django-ninja for the API unless an ADR decides otherwise.

## Milestones

1. **Skeleton:** Django project, custom user model with `auth_source`, settings via `django-environ`, `docker compose` with PostgreSQL, CI (lint + tests against PostgreSQL), base layout (full-width, dark mode via CSS variables).
2. **Auth and organisation:** local login, LDAP backend (`django-auth-ldap`, configurable, off by default), Organisation and ProductFamily models, role assignments (user or group, role, scope) inherited down the hierarchy, separation-of-duties policy (off / warn / enforce), audit history.
3. **Product model:** Product, HW variant and revision (with target markets), SW release, SW option, Configuration.
4. **Requirement packages:** JSON Schema for packages, importer, semantic linter, fixture runner, diff against previous version, approval before publish. Use a small made-up demo package for tests; real regulation packages are authored separately.
5. **Assessments:** questionnaire filtered by target markets and conditions, layered answers with provenance and override justification, carry-forward as "needs confirmation", rule evaluation into results and findings, approval with frozen snapshot, stale detection.
6. **Risk assessment:** per `docs/ARCHITECTURE.md` sections "Risk assessment: methods and catalogs" and "Risk register".
    - Method and catalog package schemas, extending the importer, linter and fixture runner from milestone 4; ship `default-cia-5x5` and a small demo catalog.
    - Product-level register with typed entries (asset, threat, hazard), threat consequences by impact category, hazard causes, and threat ↔ hazard links.
    - One rating per applicable method per entry; cross-method consistency rules; optional severity mappings.
    - Entry scoping to HW variant, SW release or option, with justified overrides; configuration views as baseline plus deltas.
    - Suggestions from applicability answers and findings via catalog triggers (accept, or dismiss with a reason).
    - Treatment and residual rating against acceptance thresholds; Control as its own entity linked to threats and hazard causes. Evidence is out of scope for this milestone.
    - Approval snapshot per configuration view, recording method and catalog versions; stale detection.
    - Extend the demo seed with Aavistin's risk register (see "Demo seed").
7. **Evidence:** not yet designed.
