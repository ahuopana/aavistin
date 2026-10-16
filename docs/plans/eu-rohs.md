# Plan: EU RoHS package (`eu-rohs`)

Status: proposal, not a decision. Nothing here is built. Legal facts below are from memory of Directive 2011/65/EU and must be checked against the Official Journal text (CELEX `32011L0065`) before they go into a package.

## 1. What the regulation is

RoHS 2 (Directive 2011/65/EU, recast) restricts hazardous substances in electrical and electronic equipment (EEE). It is a CE-marking directive with the same operator structure and module A route as `eu-lvd`, so the package shape follows `eu-lvd` closely (ADR 0045).

- **Scope (Art. 2, Art. 3):** EEE that depends on electric currents or electromagnetic fields to work, rated up to 1000 V AC / 1500 V DC. There is no lower voltage limit, unlike the LVD. "Open scope" since 22 July 2019: all EEE in, unless excluded; Annex I's 11 categories matter now mainly for transition dates and which exemptions apply.
- **Exclusions (Art. 2(4)):** military and defence, space, large-scale stationary industrial tools, large-scale fixed installations, means of transport for persons or goods, non-road mobile machinery for professional use only, active implantable medical devices, permanently installed photovoltaic panels, B2B R&D equipment, and the Art. 2(4)(j) cases. Verify the exact list and wording.
- **Substance limits (Art. 4, Annex II):** per homogeneous material, 0.1 % for lead, mercury, hexavalent chromium, PBB, PBDE and the four phthalates (DEHP, BBP, DBP, DIBP; Delegated Directive 2015/863), 0.01 % for cadmium.
- **Exemptions:** Annex III (general) and Annex IV (medical devices and monitoring and control instruments), each with expiry dates and renewals. Spare parts and cables have their own rules (Art. 4(3)-(4)).
- **Operators:** manufacturer (Art. 7), authorised representative (Art. 8), importer (Art. 9), distributor (Art. 10), importer or distributor treated as manufacturer (Art. 12).
- **Conformity:** internal production control (module A), technical documentation (harmonised standard EN IEC 63000 supports it), EU declaration of conformity (Art. 13), CE marking (Art. 14), documentation kept 10 years (Art. 7).
- **Transition dates:** categories 1–7, 10, 11 from 3 Jan 2013; medical devices and monitoring and control instruments from 22 July 2014, in vitro diagnostics from 22 July 2016, industrial monitoring and control from 22 July 2017; all other EEE from 22 July 2019. Phthalates: 22 July 2019, or 22 July 2021 for medical devices and monitoring and control instruments. Verify each.

## 2. Package design

Source `eu-rohs`, version `2011-65@2026-10` (the `eu-lvd` naming scheme), jurisdiction EU, `redistributable: true`, `dates_of_application.from: 2013-01-03`.

**Scope rule.** Include when the product is hardware (not `standalone_software` / `software_component`) and either voltage rating is at most 1000 V AC / 1500 V DC or unanswered; the "depends on electric currents" test is its own boolean (`eee_depends_on_electric_current`), so mechanical-only products drop out. While answers are missing nothing is hidden, as in LVD.

**Exclusions** (each with `id`, `when`, `ref`): `not_commercial_activity`, `military_or_defence` (reuse `is_exclusively_defence_product`), `space`, `large_scale_stationary_industrial_tool`, `large_scale_fixed_installation`, `means_of_transport`, `non_road_mobile_machinery_professional`, `active_implantable_medical_device`, `permanent_photovoltaic_panel`, `b2b_research_and_development`. The last eight come from one choice question, `rohs_exclusion_category`, as with LVD's `lvd_annex_ii_category`. Items that are interpretations (large-scale thresholds, "fixed installation") are labelled as such in `ref` and guidance.

**Roles.** Same `role` expression as `eu-lvd` (importer or distributor placing under own name or modifying becomes manufacturer, Art. 12).

**Requirements** (all `applies_from` 2013-01-03 unless the category date differs, using `applies_when` on `rohs_category`):
- Manufacturer: Art. 4 substance restriction (one requirement, plus a second for the phthalates with its own date), Art. 7 duties (design and manufacture compliant, technical documentation, module A, series production control, type/batch/serial identification, name and address, corrective action, cooperation with authorities), Art. 13 declaration of conformity, Art. 14 CE marking, retain documentation 10 years.
- Authorised representative, importer, distributor: Art. 8, 9, 10 duties (importer and distributor verify marking and documentation, only supply compliant EEE).
- Medical and monitoring/control categories: transition date requirements.

**Route.** `module_a_internal_production_control`, `allowed_when: true`.

**Findings** (`finding_rules`): partial or missing material declarations from suppliers (action required); an exemption relied on whose expiry date has passed (action required); an exemption relied on with no recorded expiry (caution); phthalate compliance not checked (action required for in-scope categories from their date); documentation, DoC and CE marking gaps; unchecked supplier (importer, distributor); importer acting as manufacturer; steward chosen as role; spare part or cable (info, partly exempt); product placed before the category's transition date (info); out of scope below nothing, but an info finding when the product is hardware without an electric function ("not EEE").

**Questions** (new ids in the package unless noted):

| Id | Type | Level | Notes |
|---|---|---|---|
| `eee_depends_on_electric_current` | boolean | hardware | Scope test (Art. 3(1)) |
| `rohs_category` | choice (Annex I 1–11) | hardware | Drives dates, Annex IV |
| `rohs_exclusion_category` | choice | product | Art. 2(4) |
| `ac_voltage_rating`, `dc_voltage_rating` | number (V) | hardware | **Move to `common`** (see decision 1) |
| `rohs_is_spare_part_or_cable` | boolean | hardware | Art. 4(3)-(4) |
| `rohs_supplier_declarations_collected` | boolean | hardware | Materials declarations for components |
| `rohs_substances_verified` | choice: `testing`, `supplier_declarations`, `both`, `none` | hardware | Evidence of limits |
| `rohs_phthalates_checked` | boolean | hardware | Delegated Directive 2015/863 |
| `rohs_relies_on_exemption` | boolean | hardware | Annex III / IV |
| `rohs_exemption_expiry` | date | hardware | Earliest expiry among exemptions used; condition `rohs_relies_on_exemption`. No per-exemption list (decision 2) |

Reused from `common` 1.4.0: `product_form`, `economic_operator_role`, `places_under_own_name_or_modifies`, `is_commercial_activity`, `is_medical_device`, `is_in_vitro_diagnostic`, `is_exclusively_defence_product`, `is_marine_equipment`, `is_civil_aviation_product`, `is_exclusively_vehicle_component`, `hardware_still_placed_on_market`, `hardware_last_placed_on_market`, `hardware_first_placed_on_market`, `technical_documentation_complete`, `eu_declaration_of_conformity_drawn_up`, `ce_marking_affixed`, `product_identification_marked`, `supplier_conformity_checked`. `safety_risk_assessment_documented` and the electrical-ratings question are LVD-specific and not reused.

**Fixtures** (about 30, each with `as_of`): a mains kettle and a Wi-Fi router (in scope, manufacturer); a low-voltage toy-like gadget (in scope, no lower limit); each Art. 2(4) exclusion; standalone software (out); a mechanical-only product (out); each role; importer acting as manufacturer; expired-exemption and no-expiry findings; unverified phthalates; medical device before and after the 2014 date; spare part; DC-only equipment below 75 V (RoHS yes, LVD no); a unit placed before 2013.

## 3. Shared-library changes

`common` 1.5.0 (supersedes 1.4.0, 1.4.0 stays for existing installs):
- Add `ac_voltage_rating` and `dc_voltage_rating`, moved from `eu-lvd`, same type, level and guidance, so both directives ask one question.
- `rohs_category` stays package-local; only the voltage ratings are genuinely shared.
- Re-run `eu-cra`, `eu-red`, `eu-lvd` fixtures against 1.5.0; none changes outcome.

`eu-lvd` 1.2.0 (supersedes 1.1.0): `uses` the two ratings from `common` instead of declaring them. Behaviour unchanged. Also update its limitation text: RoHS interplay is now modelled as a sibling package, not as LVD logic.

## 4. Decisions to confirm before building

1. **Move the voltage ratings to `common`?** Recommended: yes. The alternative (RoHS declares its own `max_ac_voltage` / `max_dc_voltage`) makes users answer the same thing twice and risks diverging answers. Cost: a `common` bump and an `eu-lvd` re-version.
2. **Exemptions: generic or listed?** Recommended: generic (`rohs_relies_on_exemption` plus earliest expiry date). Annex III/IV change by delegated acts every year or two, and a list would go stale and carry legal text. A later package version can add a catalog if wanted.
3. **Category granularity.** Recommended: model `rohs_category` as a choice of the 11 Annex I categories only to drive transition dates and Annex IV, not to restrict scope (open scope).
4. **Cross-package behaviour.** Unlike LVD and RED, RoHS, LVD and RED can all apply at once (no mutual exclusion), as a declaration of conformity usually covers them together. No fallback rules like ADR 0047. Confirm.
5. **Related-regime scope.** Out of scope for the first version: REACH Art. 33 (SVHC), WEEE, batteries regulation, ecodesign, and the Chinese/UK equivalents. Mention in the README's limitations.

## 5. Work breakdown

1. **ADR 0048** `eu-rohs-package.md` recording decisions 1–5 (next free number after 0047).
2. `common` 1.5.0 plus `eu-lvd` 1.2.0; update `packages/common/README.md`, `packages/eu-lvd/README.md` and their ADR addenda; run `ruff` and the package test suite (`apps/packages/tests.py` has the cross-package tests).
3. `packages/eu-rohs/1.0.0.json` and a `README.md` (what it is, dependencies, import/approve commands; ADR 0024), including the "not legal advice, not yet legally reviewed" banner and the legal-review list: article references, exclusion wording, the interpretive large-scale/fixed-installation thresholds, transition dates, phthalate dates.
4. Linter and fixture runner pass; add a cross-package test (a kettle is in scope for LVD and RoHS; a 12 V DC gadget only for RoHS; a defence radio is out of RoHS but falls back to LVD per ADR 0047).
5. Update the demo seed expectation (software-only Aavistin is out of RoHS), `packages/README.md` if it lists packages, the user guide where regulations are listed, and the `docs/architecture.md` mention of first-target packages if present.
6. Summary of what was built and what was deferred (exemption catalog, REACH, WEEE).

Estimated size: one ADR, one new package of about 25 requirements, 10 questions and 12 finding rules, two re-versioned packages, about 30 fixtures.
