# eu-cra

The EU Cyber Resilience Act, Regulation (EU) 2024/2847 (CELEX `32024R2847`), as a requirement package. It follows the plan in `docs/plans/eu-cra-full.md` and the Commission guidance on the application of the CRA, C(2026) 5252 ([document](https://ec.europa.eu/newsroom/dae/redirection/document/131456)).

**Not legal advice, and not yet legally reviewed.** The Annex III/IV category names, the article references in `ref` fields and the conformity routes were written from the regulation's structure and the Commission guidance, and must be checked against the Official Journal text before the package backs a real compliance decision. The review list is in the plan (section 7).

## What it covers

- **Scope:** products with a data connection; software only if it runs on the user's side (web apps used only through a browser are out). Excluded: no commercial activity (unless you are an open-source steward), medical and in-vitro diagnostic devices, type-approved vehicle parts, civil aviation, marine equipment, identical spare parts, national security, defence, and products designed to process classified information (national rules apply to those instead).
- **Roles:** manufacturer, importer, distributor, authorised representative, open-source steward. An importer or distributor that places the product under its own name or substantially modifies it is treated as the manufacturer.
- **Classification:** one core-functionality category from Annex III (class I, class II) or Annex IV, or none (default). The choices use the official category names; attribution is in the User Guide.
- **Requirements:** Annex I Part I (14) and Part II (8), the manufacturer obligations of Articles 13, 28, 30, 31 and 32, Article 14 reporting, and the obligations of authorised representatives (Art. 18), importers (Art. 19), distributors (Art. 20) and stewards (Art. 24).
- **Dates:** Article 14 reporting is in force from 11 September 2026, for all in-scope products. Everything else is in force from 11 December 2027 and applies only to products placed on the market from then on (hardware: any unit placed then; software: a release first placed then, including substantially modified releases). While no placement date is answered, nothing is hidden.
- **Routes:** internal control (default; class I with a harmonised standard covering the core functionality; class I or II open source), modules B+C and H, EU cybersecurity certification.
- **Findings:** third-party assessment needed, support period too short, substantial modification, unfinished software and preview features, security gaps (shared default passwords, no or unverified updates, unprotected data, no SBOM or CVD policy), and informational notes.
- **Fixtures:** 34 example products, most taken from the guidance's numbered examples.

Shared facts (product form, data connection, role, exclusions, placement dates, security properties, development process) come from the shared question library `packages/common` 1.1.0 and are reused by other packages.

## Known limitations

- Part II vulnerability handling ends when the support period ends. Rules don't compare with the assessment date (ADR 0018), so Part II stays listed after the support end date.
- A configuration still needs a hardware revision. Standalone software sets its markets on the software release (ADR 0020) and uses a nominal hardware entry.
- Harmonised standards are not cited yet; the question about them stays generic.

## Importing

Import and approve the shared question library first, then this package. Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.1.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.1.0
docker compose exec web python manage.py import_package packages/eu-cra/1.0.0.json --kind requirement --official
docker compose exec web python manage.py approve_package eu-cra "2024-2847@2026-10"
```

The file is named `1.0.0.json`; the package's own `version` field, which `approve_package` keys on, is `2024-2847@2026-10`. Content changes always bump that version: `RequirementPackage` is unique on `source` + `version`, and the questionnaire reads the approved copy in the database, not this file.
