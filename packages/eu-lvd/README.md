# eu-lvd

The EU Low Voltage Directive, Directive 2014/35/EU (CELEX `32014L0035`), as a requirement package. It applies from 20 April 2016 and replaced Directive 2006/95/EC. Further reading: the Commission's [LVD page and guidelines](https://single-market-economy.ec.europa.eu/sectors/electrical-and-electronic-engineering-industries-eei/low-voltage-directive-lvd_en).

**Not legal advice, and not yet legally reviewed.** The article references in `ref` fields, the requirement summaries and the interpretations marked below were written from the directive's structure and the Commission guidelines, and must be checked against the Official Journal text before the package backs a real compliance decision. Design decisions: `docs/adr/0045-eu-lvd-package.md`.

## What it covers

- **Scope (Art. 1):** electrical equipment rated 50–1000 V AC or 75–1500 V DC at its inputs or outputs. Software products are out. While a voltage rating is unanswered, nothing is hidden.
- **Exclusions:** the Annex II categories (explosive atmospheres, medical and radiology equipment, lift parts, electricity meters, domestic plugs and sockets, electric fence controllers, specialised ship, aircraft and railway equipment, custom R&D evaluation kits), supply outside a commercial activity, and two interpretations from the Commission guidelines: basic components whose safety depends on how they are built in, and radio equipment, whose electrical safety is assessed under RED Art. 3(1)(a). Radio equipment is defined as `eu-red` defines its scope (ADR 0023): a radio that is physically disabled, or that only a manufacturer update can enable, leaves the product under LVD with a caution. From 1.1.0, radio equipment that RED itself excludes because it is used exclusively for defence or public or State security (RED Art. 1(4)) also stays under LVD, with a caution about Art. 346 TFEU (ADR 0047).
- **Roles:** manufacturer, importer, distributor, authorised representative. An importer or distributor that places the product under its own name or modifies it is treated as the manufacturer (Art. 10).
- **Requirements:** the Annex I safety objectives (8, one per point), the manufacturer obligations of Art. 6 with the declaration of conformity and CE marking (Art. 15–17), the obligations of authorised representatives (Art. 7), importers (Art. 8) and distributors (Art. 9), and identification of economic operators (Art. 11). All in force from 20 April 2016.
- **Route:** internal production control (module A, Annex III). The directive has no third-party route.
- **Findings:** below or above the voltage ranges, radio equipment (assess under RED), a disabled radio, radio equipment outside RED for defence or security (1.1.0), partial standards coverage, documentation and marking gaps, an unchecked supplier, an importer acting as manufacturer, steward chosen as role, and units placed before 20 April 2016 (Art. 27).
- **Fixtures:** 36 example products in 1.0.0, 40 in 1.1.0 (a mains kettle, battery and DC equipment, a mains adapter, a basic component, switchgear above the range, a Wi-Fi router, dormant radios, defence and national-security radios, each Annex II category, each role, documentation gaps).

Shared facts (product form, role, commercial activity, medical devices, radio capability and enablement, placement dates) and the safety and CE-marking process questions come from the shared question library `packages/common` 1.4.0. It adds the `hardware_without_software` product form (1.3.0) and the process questions, which `eu-red` 1.1.0 asks too (ADR 0042). The gap findings fire only while this package covers the product, so a product never gets them from both packages.

## Versions

- `1.0.0` (`2014-35@2026-10`): first version.
- `1.1.0` (`2014-35@2026-10.1`, supersedes 1.0.0): radio equipment is excluded only while RED covers it. A radio product used exclusively for defence or public or State security is outside RED (RED Art. 1(4)) and falls back to LVD, which has no such exclusion; a caution notes that a Member State may set EU product rules aside under Art. 346 TFEU. In 1.0.0 such a product was out of both packages (ADR 0047).

## Known limitations

- No harmonised standards are listed; the question about them stays generic.
- Interplay with the Machinery Regulation (electrical hazards of machinery) and with the EMC and RoHS directives is not modelled; a declaration of conformity usually covers them together.
- Requirements apply to every unit regardless of placement date; the transition from 2006/95/EC shows only as an info finding.

## Importing

Import and approve the shared question library first, then this package. Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.4.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.4.0
docker compose exec web python manage.py import_package packages/eu-lvd/1.1.0.json --kind requirement --official
docker compose exec web python manage.py approve_package eu-lvd "2014-35@2026-10.1"
```

Approving 1.1.0 supersedes an approved 1.0.0. The file names are `1.0.0.json` and `1.1.0.json`; the package's own `version` field, which `approve_package` keys on, is `2014-35@2026-10` and `2014-35@2026-10.1`. Content changes always bump that version: `RequirementPackage` is unique on `source` + `version`, and the questionnaire reads the approved copy in the database, not this file.
