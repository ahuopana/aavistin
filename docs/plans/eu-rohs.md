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

## 4. Decisions (confirmed by the user)

1. **Voltage ratings move to `common` 1.5.0**; `eu-lvd` 1.2.0 uses them from there.
2. **Exemptions: a full list, like the CRA package's Annex III/IV category list.** Revised from "generic only" at the user's request. One choice question per annex lists every current entry (number plus our own short summary and the expiry date), and the generic questions in 4a stay as the fallback for "other". Constraints:
   - **The annexes have changed since 2016.** The user believed the latest amendment was 2016. A web search found delegated directives of November 2025 (reported as 2025/1802, 2025/2363 and 2025/2364) that restructure the lead exemptions in Annex III (series 6 and 7(a), 7(c)), applying since 1 July 2026, and a mid-2026 draft amending Annexes III and IV for lead and cadmium. Those are secondary sources and unverified.
   - **The list cannot be written from memory.** ADR 0012 declined to reproduce the CRA categories from memory for the same reason. EUR-Lex is blocked in this environment (HTTP 403 from the proxy), so the consolidated text cannot be read here.
   - **Needed to proceed:** either the consolidated Annex III and IV text pasted or attached, or `eur-lex.europa.eu` allowed on the environment's network policy. Then the package records the consolidation date it was built from, and every expiry date goes in `ref`.
   - Entries are own summaries (EU legal text may be stored with attribution; no standards text is involved).
3. **LVD and RED stay mutually exclusive** (ADR 0045, 0047). **RoHS can apply alongside either**, so there are no fallback rules between RoHS and the other two.
4. **REACH and WEEE are their own regulations**, each with its own package. They are out of scope here; we stay focused on RoHS.

### 4a. Sample exemption questions

Package-local, hardware level. Exemption numbers are examples of the Annex III/IV style and must be checked against the current annexes.

```json
{
  "id": "rohs_relies_on_exemption",
  "type": "boolean",
  "level": "hardware",
  "label": "Does any homogeneous material in this hardware exceed a RoHS limit and rely on an exemption in Annex III or Annex IV?",
  "guidance": "Typical cases are lead in solder for some high-melting or server applications, lead in glass of electronic components, and cadmium in certain contacts. If you are unsure, ask the supplier of the component which exemption their declaration relies on.",
  "guidance_url": "https://environment.ec.europa.eu/topics/waste-and-recycling/rohs-directive_en"
},
{
  "id": "rohs_exemption_annex",
  "type": "choice",
  "level": "hardware",
  "label": "Which annex lists the exemption you rely on?",
  "choices": ["annex_iii", "annex_iv", "both"],
  "condition": {"==": [{"var": "rohs_relies_on_exemption"}, true]},
  "guidance": "Annex IV applies only to medical devices and monitoring and control instruments."
},
{
  "id": "rohs_exemption_reference",
  "type": "choice",
  "level": "hardware",
  "label": "Which exemption do you rely on most heavily? (sample list)",
  "choices": ["lead_in_high_melting_solder", "lead_in_glass_or_ceramic", "cadmium_in_contacts", "mercury_in_lamps", "other"],
  "condition": {"==": [{"var": "rohs_relies_on_exemption"}, true]},
  "guidance": "A short sample list; 'other' means an exemption not listed here. The package does not hold the full annexes."
},
{
  "id": "rohs_exemption_expiry",
  "type": "date",
  "level": "hardware",
  "label": "When does the earliest-expiring exemption you rely on end?",
  "condition": {"==": [{"var": "rohs_relies_on_exemption"}, true]},
  "guidance": "Look up the validity date in the current annex. Exemptions are renewed or allowed to lapse by delegated directive. After the date, the product must comply without the exemption."
}
```

Finding rules over these: `rohs_exemption_expiry` earlier than the assessment date gives an action-required finding; an empty expiry gives a caution.

## 5. Work breakdown

1. **ADR 0048** `eu-rohs-package.md` recording decisions 1–5 (next free number after 0047).
2. `common` 1.5.0 plus `eu-lvd` 1.2.0; update `packages/common/README.md`, `packages/eu-lvd/README.md` and their ADR addenda; run `ruff` and the package test suite (`apps/packages/tests.py` has the cross-package tests).
3. `packages/eu-rohs/1.0.0.json` and a `README.md` (what it is, dependencies, import/approve commands; ADR 0024), including the "not legal advice, not yet legally reviewed" banner and the legal-review list: article references, exclusion wording, the interpretive large-scale/fixed-installation thresholds, transition dates, phthalate dates.
4. Linter and fixture runner pass; add a cross-package test (a kettle is in scope for LVD and RoHS; a 12 V DC gadget only for RoHS; a defence radio is out of RoHS but falls back to LVD per ADR 0047).
5. Update the demo seed expectation (software-only Aavistin is out of RoHS), `packages/README.md` if it lists packages, the user guide where regulations are listed, and the `docs/architecture.md` mention of first-target packages if present.
6. Summary of what was built and what was deferred (exemption catalog, REACH, WEEE).

Estimated size: one ADR, one new package of about 25 requirements, 10 questions and 12 finding rules, two re-versioned packages, about 30 fixtures.
