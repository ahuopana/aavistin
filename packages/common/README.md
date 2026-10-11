# common

The shared question library: questions that several requirement packages need (product form, data connection, economic-operator role, exclusions, placement dates, security properties, development process) declared once. It is a `question_set` package, not a requirement package, so it has no requirements, scope or findings of its own.

Requirement packages reference its questions with `"uses": ["common:<question_id>"]` instead of redeclaring them. A question may declare `implied_by` to derive its value from other answers when none was given. Design: `docs/adr/0015-shared-question-library.md`.

## Versions

- `1.0.0`: the first three questions, kept for history.
- `1.1.0`: the full set used by `eu-cra`.
- `1.1.1`: reworded the "widest inbound exposure" question and added guidance.
- `1.2.0`: 1.1.1 plus the facts `eu-red` needs (radio enablement, internet connection, money transfer, toy, childcare, wearable); role and placement questions link to the Blue Guide. `eu-cra` lints clean against it.

## Importing

Import and approve this before any package that `uses` it. The importer refuses a package whose question sets are not approved (use `--force` only to break a dependency cycle). Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.2.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.2.0
```

Content changes always bump the version: `RequirementPackage` is unique on `source` + `version`, and the questionnaire reads the approved copy in the database, not this file.
