# eu-emc

The EU Electromagnetic Compatibility Directive, Directive 2014/30/EU (CELEX `32014L0030`), as a requirement package. It applies from 20 April 2016 and replaced Directive 2004/108/EC. Further reading: the Commission's [EMC Directive page and guide](https://single-market-economy.ec.europa.eu/sectors/electrical-and-electronic-engineering-industries-eei/electromagnetic-compatibility-emc-directive_en).

**Not legal advice, and not yet legally reviewed.** The article references in `ref` fields, the requirement summaries and the interpretations marked below were written from the directive's structure and the Commission guide, not checked against the Official Journal text. Article numbers other than the Annexes in particular must be verified before the package backs a real compliance decision. Design decisions: `docs/adr/0047-eu-emc-package.md`.

## What it covers

- **Scope:** electrical and electronic hardware that can generate electromagnetic disturbance or be affected by it. There is no voltage or technology threshold, so a battery-powered device is in scope. Standalone software and software components are out.
- **Equipment type** (one question): apparatus, fixed installation, component for incorporation, inherently benign equipment, or a radio amateur kit not sold commercially. The last three are excluded.
- **Exclusions:** radio equipment (its EMC is assessed under RED Art. 3(1)(b), using the same radio test as `eu-red` and `eu-lvd`, ADR 0023), civil aviation products, supply outside a commercial activity, and three interpretations marked as such in `ref`: marine equipment, medical devices and in vitro diagnostics, and the component and benign-equipment types.
- **Roles:** manufacturer, importer, distributor, authorised representative. An importer or distributor that places the apparatus under its own name or modifies it is treated as the manufacturer.
- **Requirements (28):** the Annex I(1) protection requirements (emissions, immunity), the EMC assessment and technical documentation, the declaration of conformity and CE marking, the remaining manufacturer, authorised representative, importer and distributor obligations, and identification of economic operators. For fixed installations, the two Annex I(2) requirements replace those for apparatus. All in force from 20 April 2016. While the equipment type is unanswered both sets are listed.
- **Route:** internal production control (module A, Annex II) for apparatus. Fixed installations have no conformity assessment route. The directive's optional notified-body involvement is not modelled.
- **Findings:** radio equipment (assess under RED), a disabled radio, an excluded type kept on interpretation, fixed installations (no CE marking), partial or no use of harmonised standards, documentation, use-information, declaration, CE marking and identification gaps, an unchecked supplier, an importer acting as manufacturer, steward chosen as role, and units placed before 20 April 2016.
- **Fixtures:** 32 example products (a mains kettle, a battery device, radios, each exclusion, a fixed installation, each role, documentation gaps).

Shared facts (product form, role, commercial activity, medical devices, civil aviation, marine equipment, radio capability and enablement, placement dates) and the documentation and CE-marking process questions come from the shared question library `packages/common` 1.4.0 (ADR 0042). The package asks four questions of its own: equipment type, conformity basis, use information and, for fixed installations, documentation.

## Known limitations

- **Duplicated findings with `eu-lvd`.** A mains-powered product without a radio is in scope of both packages. The shared answers (declaration of conformity, CE marking, identification, supplier check, technical documentation) each raise a finding from each package, because each package gates them with its own scope. This is accepted (ADR 0047): one declaration usually covers both directives, and each finding names its own directive.
- The shared questions are worded for apparatus, so a fixed installation is also asked about the CE marking and declaration; those answers raise no finding for it.
- Vehicle type-approval (EMC is covered by the type-approval rules), the Machinery Regulation and RoHS are not modelled.
- No harmonised standards are listed; the conformity question stays generic.
- Requirements apply to every unit regardless of placement date; the transition from 2004/108/EC shows only as an info finding.

## Importing

Import and approve the shared question library first, then this package. Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.4.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.4.0
docker compose exec web python manage.py import_package packages/eu-emc/1.0.0.json --kind requirement --official
docker compose exec web python manage.py approve_package eu-emc "2014-30@2026-10"
```

The file is named `1.0.0.json`; the package's own `version` field, which `approve_package` keys on, is `2014-30@2026-10`. Content changes always bump that version: `RequirementPackage` is unique on `source` + `version`, and the questionnaire reads the approved copy in the database, not this file.
