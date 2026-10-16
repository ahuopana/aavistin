# 47. EU EMC package

Status: Accepted (content is a first pass, not legally reviewed).

## Context

`eu-lvd` (ADR 0045) and `eu-red` (ADR 0042) already say that EMC is not modelled, and a CE declaration of conformity usually covers the EMC Directive (2014/30/EU) together with the LVD or RED. `docs/architecture.md` does not name EMC as a target, so this is a decision outside the design and is recorded here. The directive has the same shape as the LVD: one scope rule, a short exclusion list, no classes and a single conformity route for apparatus. It differs in that it has no voltage threshold and treats fixed installations separately.

## Decisions

- **`packages/eu-emc`, source `eu-emc`, version `2014-30@2026-10`**, following the `eu-lvd` layout (shared questions via `uses`, question groups, role expression, per-role requirements, fixtures with `as_of`). It needs `common` 1.4.0 and changes nothing in it.
- **Scope has no voltage test.** Any hardware product is in scope unless excluded; standalone software and software components are out. A battery-only device is therefore EMC-only.
- **One local question for equipment type**, with choices apparatus, fixed installation, component for incorporation, inherently benign, and radio amateur kit. The last three are exclusions. The component and benign types, marine equipment, and medical devices (reusing `is_medical_device` and `is_in_vitro_diagnostic`) rest on the Commission's EMC Guide or on other legislation covering EMC, and are labelled as interpretations in `ref`. Civil aviation reuses `is_civil_aviation_product`.
- **Radio equipment is excluded** with the same test as `eu-red` and `eu-lvd` (ADR 0023), because RED Art. 3(1)(b) covers its EMC. Exactly one of RED and EMC covers a product's EMC: a radio that is disabled, or enableable only by a manufacturer update, stays under EMC with a caution.
- **Fixed installations** get their own pair of requirements (Annex I(2)) through `applies_when` on the equipment type, no assessment route, and an info finding that no CE marking or declaration applies. While the type is unanswered, both sets are listed.
- **One route for apparatus, internal production control (module A).** Optional notified-body involvement is not modelled.
- **Shared process questions are reused unchanged, and duplicated findings are accepted.** A product in scope of both the LVD and the EMC Directive (a mains product without a radio) raises the declaration, CE marking, identification, technical documentation and supplier findings once from each package, because each package gates a shared answer with its own scope (ADR 0042). A single declaration usually covers both directives, but each finding names its own directive, and de-duplicating across packages would need engine support. Revisit if the duplicates read as noise in the UI. `common`'s `safety_risk_assessment_documented`, `electrical_ratings_marked` and `safety_instructions_in_local_languages` are not reused: they are LVD safety wording.
- **No placement-date conditions on requirements.** All apply from 20 April 2016. Units placed earlier under 2004/108/EC get an info finding only.

## Consequences

- Fixtures (32) cover scope, each exclusion, each role, fixed installations and the gap findings. A cross-package test shows radio equipment under RED only, a mains product without radio under LVD and EMC, a battery product under EMC only, and the accepted duplicate CE-marking finding.
- The `eu-lvd` and `eu-red` READMEs no longer say EMC is unmodelled; ADR 0045 and ADR 0042 note that EMC is now a separate package.
- Not modelled: vehicle type-approval EMC rules, the Machinery Regulation and RoHS; harmonised standards are not listed.
- The legal-review list for this package: all article numbers, the Annex I summaries, the fixed-installation treatment, the three interpretive exclusions, and the module A route against the Official Journal text.
