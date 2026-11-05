# eu-emc

The EU Electromagnetic Compatibility Directive, Directive 2014/30/EU (CELEX `32014L0030`), as a requirement package. It applies from 20 April 2016 and replaced Directive 2004/108/EC. Further reading: the Commission's [EMC Directive page and guide](https://single-market-economy.ec.europa.eu/sectors/electrical-and-electronic-engineering-industries-eei/electromagnetic-compatibility-emc-directive_en).

**Not legal advice, and not yet legally reviewed.** From 1.1.0 the article and annex references and the scope wording were checked against the Official Journal text of the directive (ADR 0050). The requirement summaries, the readings marked as applied or interpreted in `ref`, and the questions we phrase ourselves are ours and still need review before the package backs a real compliance decision. Design decisions: `docs/adr/0049-eu-emc-package.md` and `docs/adr/0050-directive-wording-and-document-retention.md`.

## What it covers

- **Scope (Art. 2, Art. 3):** electrical and electronic hardware that can generate electromagnetic disturbance or be affected by it. There is no voltage or technology threshold, so a battery-powered device is in scope. Standalone software and software components are out.
- **Equipment type** (one question): apparatus, fixed installation, component for incorporation, equipment that cannot cause or suffer disturbance by its inherent physical characteristics, radio amateur kit, or custom evaluation kit. The last four are excluded.
- **Exclusions:**
  - written in the directive: radio equipment while RED covers it (Art. 2(2)(a), assessed under RED Art. 3(1)(b), with the same radio test as `eu-red` and `eu-lvd`, ADR 0023); aeronautical products (Art. 2(2)(b)); radio amateur equipment not made available on the market (Art. 2(2)(c)); equipment that by its inherent physical characteristics can neither cause nor suffer disturbance, both parts of the test being needed (Art. 2(2)(d)); custom-built evaluation kits for professionals (Art. 2(2)(e)); and supply outside a commercial activity (Art. 3(1)(9)).
  - applied by us: marine equipment and medical devices, where other Union legislation lays down the EMC requirements more specifically (Art. 2(3)); and components with no direct function for an end-user, from the Commission's EMC Guide.
  - Radio equipment used exclusively for defence or public or State security is outside RED Art. 1(4) and falls back to this package with a caution, as in `eu-lvd` 1.1.0 (ADR 0047).
- **Roles:** manufacturer, importer, distributor, authorised representative. An importer or distributor that places the apparatus under its own name or modifies it is treated as the manufacturer (Art. 11).
- **Requirements (29):** the Annex I(1) protection requirements (emissions, immunity), the EMC assessment and technical documentation (Art. 14, Annex II), the EU declaration of conformity and CE marking (Art. 15 to 17), the other manufacturer obligations (Art. 7), the use information (Art. 18), the obligations of authorised representatives (Art. 8), importers (Art. 9) and distributors (Art. 10), and identification of economic operators (Art. 12). For fixed installations, the two requirements from Annex I(2) and Art. 19 replace those for apparatus. All in force from 20 April 2016. While the equipment type is unanswered both sets are listed.
- **Route:** internal production control (module A, Annex II) for apparatus. Fixed installations have no conformity assessment route.
- **Findings:** radio equipment (assess under RED), a disabled radio, a defence or security radio that falls back to this package, an exclusion to keep the reasoning for, fixed installations (no CE marking), partial or no use of harmonised standards, documentation, retention, use-information, EU declaration of conformity, CE marking and identification gaps, an unchecked supplier, an importer acting as manufacturer, steward chosen as role, and units placed before 20 April 2016 (Art. 43).
- **Fixtures:** 37 example products (a mains kettle, a battery device, radios, defence and security radios, each exclusion, a fixed installation, each role, documentation gaps).

Shared facts (product form, role, commercial activity, medical devices, civil aviation, marine equipment, radio capability and enablement, placement dates) and the documentation and CE-marking process questions, including the 10-year retention question, come from the shared question library `packages/common` 1.5.0 (ADR 0042, ADR 0050). The package asks four questions of its own: equipment type, conformity basis, use information and, for fixed installations, documentation of the good engineering practices.

## Versions

- `1.0.0` (`2014-30@2026-10`): first version, written before the directive text was checked.
- `1.1.0` (`2014-30@2026-11`, supersedes 1.0.0): checked against the Official Journal (ADR 0050). Sub-article references on the obligations; the inherent-characteristics exclusion renamed after Art. 2(2)(d) (the choice id changes, so answers to the old choice are unanswered again); the custom evaluation kit exclusion added (Art. 2(2)(e)); the use-information question and requirement follow Art. 18; the importer obligations follow Art. 9 (instructions duty added, sample-testing duty removed, which belongs to the LVD); the fixed-installation documentation follows Art. 19(1); a retention question and finding (Art. 7(3)). Needs `common` 1.5.0.

## Known limitations

- **Duplicated findings with `eu-lvd`.** A mains-powered product without a radio is in scope of both packages. The shared answers (EU declaration of conformity, CE marking, identification, supplier check, technical documentation and its retention) each raise a finding from each package, because each package gates them with its own scope. This is accepted (ADR 0049): a single EU declaration of conformity covers all the Union acts (Art. 15(3)), and each finding names its own directive.
- The shared questions are worded for apparatus, so a fixed installation is also asked about the CE marking and declaration; those answers raise no finding for it.
- **Conformity route (b) is not modelled.** Art. 14 also allows EU type examination followed by conformity to type (Annex III), with a notified body. Only internal production control is offered.
- **Apparatus made only for one particular fixed installation** is exempt from most articles under Art. 19(1) but must come with documentation that identifies the installation. There is no equipment type for it yet.
- Vehicle type-approval (EMC is covered by the type-approval rules), the Machinery Regulation and RoHS are not modelled.
- No harmonised standards are listed; the conformity question stays generic.
- Requirements apply to every unit regardless of placement date; the transition from 2004/108/EC shows only as an info finding.

## Importing

Import and approve the shared question library first, then this package. Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.5.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.5.0
docker compose exec web python manage.py import_package packages/eu-emc/1.1.0.json --kind requirement --official
docker compose exec web python manage.py approve_package eu-emc "2014-30@2026-11"
```

Approving 1.1.0 supersedes an approved 1.0.0. The file names are `1.0.0.json` and `1.1.0.json`; the package's own `version` field, which `approve_package` keys on, is `2014-30@2026-10` and `2014-30@2026-11`. Content changes always bump that version: `RequirementPackage` is unique on `source` + `version`, and the questionnaire reads the approved copy in the database, not this file.
