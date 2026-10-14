# common

The shared question library: questions that several requirement packages need (product form, data connection, economic-operator role, exclusions, placement dates, security properties, development process) declared once. It is a `question_set` package, not a requirement package, so it has no requirements, scope or findings of its own.

Requirement packages reference its questions with `"uses": ["common:<question_id>"]` instead of redeclaring them. A question may declare `implied_by` to derive its value from other answers when none was given. Design: `docs/adr/0015-shared-question-library.md`.

## Versions

- `1.0.0`: the first three questions, kept for history.
- `1.1.0`: the full set used by `eu-cra`.
- `1.1.1`: reworded the "widest inbound exposure" question and added guidance.
- `1.2.0`: 1.1.1 plus the facts `eu-red` needs (radio enablement, internet connection, money transfer, toy, childcare, wearable); role and placement questions link to the Blue Guide. `eu-cra` lints clean against it.
- `1.3.0`: 1.2.0 plus the `hardware_without_software` product form, for electrical products with no programmable parts (used by `eu-lvd`). `eu-cra` and `eu-red` pass against it.
- `1.4.0`: 1.3.0 plus product-safety and CE-marking process questions shared by `eu-lvd` and `eu-red` 1.1.0 (safety risk assessment, technical documentation, electrical ratings, declaration of conformity, CE marking, identification, instructions in local languages, supplier checks; ADR 0042).

## Importing

Import and approve this before any package that `uses` it. The importer refuses a package whose question sets are not approved (use `--force` only to break a dependency cycle). Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.4.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.4.0
```

Content changes always bump the version: `RequirementPackage` is unique on `source` + `version`, and the questionnaire reads the approved copy in the database, not this file.
