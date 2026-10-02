# Plan: full EU CRA package (`eu-cra`)

Status: draft for review. Nothing here is decided until it lands as an ADR or in `docs/architecture.md`.

Inputs:

- Regulation (EU) 2024/2847 (CRA), CELEX `32024R2847`.
- Commission guidance on the application of the CRA, C(2026) 5252, 27.7.2026 ([document](https://ec.europa.eu/newsroom/dae/redirection/document/131456)). Section numbers below ("G 6.1") refer to it.
- Commission Implementing Regulation (EU) 2025/2392: technical descriptions of the Annex III/IV categories.
- Commission Delegated Regulation (EU) 2025/1535: excludes L-category vehicles (Regulation (EU) No 168/2013).
- Overlap research on IEC 62443 and NIST SSDF (section 5).

## 1. Goal

`eu-cra` is the full CRA package. It replaces the current scaffold outright: Aavistin has no real users before version 1.0, so there is no migration, coexistence or withdrawal to design. The change that adds `eu-cra` deletes the scaffold package and moves its tests over. ADR 0012's rename addendum assumed the scaffold would live on beside a full package, so that addendum gets superseded in the same change.

**Time-sensitive:** the Article 14 reporting obligations have applied since **11 September 2026**, to every in-scope product, including those placed on the market before 11 December 2027, and they continue after the support period ends (G 9.1). Today's package has only one, package-level application date, so it can't show this. See 6.1.

## 2. What the guidance changes for our model

| Guidance | What it settles | Package construct |
| --- | --- | --- |
| G 2.2, 2.5 | Software executed on the user's side is a product; software only accessed remotely through a browser (web apps, websites) is not, unless it is RDPS of a product. A data connection means deliberately encoded digital data, not mere on/off signalling. | Scope questions 3.1 |
| G 2.1 | Software variants that differ in components, configuration or features are distinct products; copies of one version are placed together. | Fits HW variant / SW release / option; no change |
| G 2.4 | Companion software needed to operate the hardware (apps, drivers) is part of the product, even when delivered separately. | Guidance text on the product-form question |
| G 2.6, 2.7 | Essential requirements apply through the risk assessment; a requirement can be not applicable or met by compensating measures, documented. Legacy designs need no redesign if the risk assessment shows adequate measures. | Requirement status "not applicable, justified" in assessments (6.7); info finding for legacy designs |
| G 3 | FOSS = OSS licence **and** publicly shared source; placed on the market only if monetised (price, monetising other services, data processing as a condition of use, donations that are de facto required). Stewards have Article 24 obligations. | FOSS and role questions 3.1, 3.2 |
| G 4.2 | Spare-part exemption only when supplied for repair of an identified product **and** identical in security-relevant characteristics (algorithms, protocols, crypto, access control). | Two questions, one derived exclusion |
| G 4.3 | Substantial modification of software: four tests (new threat vectors, new attack scenarios, changed likelihood, changed impact) plus a change of intended purpose, unless already covered by the risk assessment. Security updates generally aren't substantial. | Per-release questions 3.5; finding "new conformity assessment" |
| G 5 | Support period ≥ 5 years unless the expected use time is shorter, and longer when expected use is longer. Article 13(10): software may remediate only the latest version if upgrading is free and causes no additional costs. | Numeric questions 3.4; findings |
| G 6.1 | Classification by **one** core functionality; ancillary functions and integrated components don't change it; products that substantially exceed or fall short of a category are not in it; separately sold modules are classified separately. | Single-choice category question 3.3 |
| G 6.2, 6.3 | Class I may use internal control only if a cited harmonised standard (or common specification or EUCC at "substantial") covers all risks of the core functionality. FOSS important products may always use internal control (Art. 32(5)). | Assessment routes 4.3 |
| G 7.3, 7.4 | Due diligence on integrated components is distinct from the risk assessment; product families sharing a security profile can share one risk assessment and declaration of conformity. | Process questions; aligns with answer inheritance |
| G 8 | Remote data processing solution (RDPS) = processing at a distance **and** its absence would prevent a function **and** designed by or for the manufacturer (IaaS/PaaS-hosted code yes, third-party SaaS no). | Three questions + one derived 3.1 |
| G 9.1 | Reporting since 11.9.2026; 24 h early warning, 72 h notification, final report within 14 days after a fix (vulnerabilities) or 1 month (incidents). Part II vulnerability handling doesn't apply to products placed before 11.12.2027 or after the support period ends. | Per-requirement dates and conditions 6.1 |
| G 9.2 | "Known" vulnerability = listed in public databases or known through non-public channels; upstream reporting only for the integrated version, not when the maintainer already knows or no maintainer exists. | Requirement labels and guidance text |
| G 9.3 | Vehicle components excluded only when exclusively designed for M/N/O or L-category vehicles (the distribution channel is evidence). RED delegated-act or Machinery Regulation certificates remain usable for covered risks until 11.6.2028. | Exclusion question with guidance; info finding |

## 3. Question catalogue (draft)

"common" = proposed for `packages/common` (shared with other packages); otherwise declared in `eu-cra`. Levels follow ADR 0004. Labels are working titles; each self-assessed question gets `guidance` and a `guidance_url` pointing at the relevant guidance section (ADR 0014).

### 3.1 Scope

| id | type | level | drives | notes |
| --- | --- | --- | --- | --- |
| `has_data_connection` | boolean | software | scope include | common; `implied_by` an interface present (true only). Guidance: G 2.5 (encoded data vs on/off signalling). |
| `product_form` | choice: standalone software · hardware with software · hardware component · software component | product | scope; Art. 13(10) | common (62443 and SSDF also distinguish component vs product). |
| `software_executes_on_user_side` | boolean | software | scope (web-only apps out) | `condition`: standalone software. G 2.2. |
| `is_free_and_open_source` | boolean | product | scope, Art. 32(5) route | moved to common; guidance from G 3 (two-part test). |
| `is_commercial_activity` | boolean | product | scope | moved to common; guidance from G 3.2. |
| `is_unfinished_software_release` | boolean | software | Art. 4(3) caution | the whole build is alpha/beta/RC, made available only for testing, for a limited time, with a visible non-compliance notice. |
| `release_has_preview_features` | boolean | software | caution | the release is a normal one but some features are labelled beta/experimental. Art. 4(3) does not cover these (see 4.4). |
| `remote_processing_at_distance` | boolean | software | RDPS | G 8.1.1 |
| `remote_processing_needed_for_function` | boolean | software | RDPS | G 8.1.2 (telemetry for statistics only: no) |
| `remote_processing_designed_by_manufacturer` | boolean | software | RDPS | G 8.1.3 (own code on IaaS/PaaS: yes; third-party SaaS: no) |
| `has_remote_data_processing` | boolean | software | requirements cover RDPS | derived: `implied_by` the three above. |
| `is_medical_device`, `is_in_vitro_diagnostic` | boolean | product | Art. 2(2) exclusions | common (RED, MDR, LVD reuse the exclusions below too). |
| `is_exclusively_vehicle_component` | boolean | product | Art. 2(2)(c) + DA 2025/1535 | guidance: exclusively designed, channel matters (G 9.3.1). |
| `is_civil_aviation_product`, `is_marine_equipment` | boolean | product | Art. 2(3), 2(4) exclusions | |
| `is_exclusively_national_security_product` | boolean | product | Art. 2(7) | common: separate facts, because other legislation treats them differently (e.g. defence-only matters for dual-use and procurement rules). |
| `is_exclusively_defence_product` | boolean | product | Art. 2(7) | common |
| `processes_classified_information` | boolean | product | Art. 2(7) | common; "specifically designed to process classified information" is the third case in the same article. |
| `supplied_as_spare_part`, `spare_part_security_identical` | boolean | hardware | Art. 2(6) | exclusion when both true (G 4.2). |
| `hardware_first_placed_on_market`, `hardware_last_placed_on_market` | date | hardware | Part II, Art. 69(2), reference dates for requirements (4.1.1) | common. Hardware units are placed one by one (G 2.1, Blue Guide), so a revision straddling 11.12.2027 has units on both sides; "last" stays empty while units still ship. Needs a `date` question type (6.8). |
| `software_first_placed_on_market` | date | software | same | common. All copies of a version count as placed at its first offering (G 2.1), so one date per release is enough; a non-substantial release keeps the date of the release it updates (Example 2). |

### 3.2 Economic operator role

| id | type | level | drives |
| --- | --- | --- | --- |
| `economic_operator_role` | choice: manufacturer · importer · distributor · authorised representative · open-source steward | product | which requirements apply (needs 6.2); common, shared by all EU product-legislation packages |
| `places_under_own_name_or_modifies` | boolean | product | Art. 21/22: importer or distributor becomes manufacturer |

### 3.3 Classification

| id | type | level | drives |
| --- | --- | --- | --- |
| `core_functionality_category` | choice: "none" + Annex III class I (19), class II (4), Annex IV (3) | product | classifications `default`, `important_class_i`, `important_class_ii`, `critical` via `in` |

One choice, not a multi-select: G 6.1 (point 144) says a product has exactly one core functionality for this purpose. **Decided:** the choices use the full official category names (EU legal text, allowed with attribution per `docs/architecture.md`, Copyright); the attribution lives in the User Guide. The technical descriptions in Implementing Regulation 2025/2392 are linked, not copied. The guidance text carries the G 6.1 test: main purpose, not ancillary functions or integrated components; substantially exceeds or falls short → not that category; modules sold separately are classified separately.

The category list must be checked against the Official Journal text when it is encoded. The plan's working list (class I: identity/privileged access management, browsers, password managers, anti-malware, VPN, network management, SIEM, boot managers, PKI, network interfaces, operating systems, routers/modems/switches, microprocessors, microcontrollers, ASIC/FPGA with security functions, smart home virtual assistants, smart home security products, connected toys, health and children's wearables; class II: hypervisors and container runtimes, firewalls/IDS/IPS, tamper-resistant microprocessors and microcontrollers; Annex IV: hardware devices with security boxes, smart meter gateways and secure cryptoprocessing devices, smartcards and secure elements) is from memory.

### 3.4 Conformity route and support period

| id | type | level | drives |
| --- | --- | --- | --- |
| `harmonised_standards_cover_core_functionality` | boolean | product | class I may use module A (G 6.2, point 149) |
| `has_prior_cybersecurity_type_exam_certificate` | boolean | hardware | info: RED DA / Machinery certificate usable until 11.6.2028 (G 9.3.2) |
| `expected_use_time_years` | number (years) | product | support period findings |
| `support_period_end` | date | product | support period findings; Part II ends on it (4.1.1). The end date is what Art. 13(19) requires telling users anyway (at least month and year). |
| `latest_version_remediation_only` | boolean | software | Art. 13(10), `condition`: software product |
| `designed_before_cra_application` | boolean | product | info finding (G 2.7) |

Support period findings, with the support length = years from the placement date to `support_period_end` (needs date arithmetic, 6.8): action required if it is under 5 while `expected_use_time_years` ≥ 5, or shorter than an expected use time under 5 years; caution if it is shorter than a longer expected use time (G 5, recital 60).

### 3.5 Per software release: substantial modification

All at `software` level, answered per release. Copy-forward is wrong for these (a release's deltas don't carry over), see 6.4.

| id | test (G 4.3, point 110) |
| --- | --- |
| `release_changes_intended_purpose` | intended purpose changed |
| `release_adds_threat_vectors` | new interfaces, channels, execution environments or external dependencies |
| `release_enables_new_attack_scenarios` | new ways to gain access, manipulate or misuse |
| `release_changes_attack_likelihood` | lower effort or expertise, more exposure, weaker safeguards |
| `release_changes_attack_impact` | wider data or functions affected, worse consequences, harder detection or recovery |
| `release_changes_covered_by_risk_assessment` | the new risks were already foreseen and mitigated |
| `is_substantial_modification` | derived: any of the first five and not the sixth |

Findings: substantial modification → action required: new conformity assessment, new placing on the market, declare a support period for this version (G 4.4.2, 5.1).

### 3.6 Product security properties (Annex I Part I)

CRA Part I is risk-based ("where applicable"), so these questions don't decide compliance. They raise findings and help fill the requirement status. Most of them overlap with IEC 62443-4-2 and SSDF and belong in `common`. The list comes from section 5. It follows the architecture's capability vs enablement split (hardware capability, software enablement), e.g. debug interfaces present in hardware, disabled in the release.

### 3.7 Manufacturer process (Annex I Part II, Art. 13, Art. 14)

Process facts: CVD policy, vulnerability contact point, SBOM production, security testing before release and regular review, advisories, free and separate security updates, secure update distribution, upstream reporting (Art. 13(6)), component due diligence (Art. 13(5)), documented risk assessment, readiness for the ENISA single reporting platform. They overlap most with IEC 62443-4-1 and SSDF (section 5).

**Decided:** answered per product (standing policies at `product` level, per-release activities at `software` level), not at organisation or family level. Different product teams run different processes; a new team may work more agile than a mature product line. No new answer level is needed.

## 4. Requirements, routes, findings, fixtures

### 4.1 Requirements

Full coverage, each with `ref`, `roles`, classes, application dates and a condition (needs 6.1, 6.2). **Decided:** all economic operator roles from the start, not manufacturer only.

#### 4.1.1 Application dates: start, end, and against which date

An end date is needed, but a start or end date alone is ambiguous: it matters which date it is compared with. Comparing everything with "today" would be wrong for half of the CRA.

| Case | Example | Compare with |
| --- | --- | --- |
| Duty from a date on, whatever the product's age | Art. 14 reporting, from 11.9.2026, also for products placed earlier and after support ends (G 9.1) | assessment date |
| Duty for products placed from a date on | Annex I essential requirements and Part II, from 11.12.2027; a unit placed in 2026 never becomes subject (only Art. 14 reaches it) | placement date |
| A window that closes | Art. 69(1): RED delegated-act or Machinery certificates count for covered risks only until 11.6.2028 | placement date |
| A standard replaced, fully or partly | When a revised harmonised standard is cited, the OJ notice gives the old version a date of cessation of presumption of conformity. Products placed before it keep the presumption under the old version; units placed later need the new one. | placement date |
| Duty that ends with the product's own lifecycle | Part II ends when the support period ends | a condition on the product's support end date, not a fixed date |

What this means for the design:

- Each `applies_from` / `applies_until` (requirement and package level) says its **basis**: `placement` or `assessment`. The placement date comes from the questions in 3.1; for hardware, a requirement with a placement-based start applies if any units are placed on or after it (last placement empty or later).
- **Partial supersession of a standard** (raised in review) is handled without new machinery. The old standard package keeps the clauses that weren't replaced, and the replaced ones get `applies_until` = cessation date, basis `placement`. The new package `amends` the old one. Products placed before cessation are still assessed against the old clauses. A whole-standard replacement uses the package-level `until` the same way.
- **Why not just version the package?** Versioning covers law that changes going forward. It can't express "the same text stops counting on date D for products placed after D" (Art. 69(1), cessation of presumption) while older products keep it. So the requirement-level end date is cheap and does real work.
- **Old assessments are not reinterpreted.** Approval freezes package versions and results (snapshots). But an assessment-date rule can change meaning while a product is still on the market: Art. 14 switched on in September 2026. The existing staleness job (ADR 0007) should flag approved assessments when a date they depend on passes.
- **Show, don't hide.** A requirement that isn't in force yet, or no longer is, appears with its dates ("applies from 11.12.2027", "until 11.6.2028 for products placed by then"). Users plan for what is coming.

Requirement groups:

- Annex I Part I: (1) and (2)(a)–(m), 14 items.
- Annex I Part II: (1)–(8). Not for products placed before 11.12.2027 or past their support period.
- Article 13 manufacturer obligations: risk assessment, due diligence, support period and its communication, technical documentation (Annex VII), user information (Annex II), declaration of conformity (Annex V/VI), CE marking (Art. 30), upstream reporting, retention.
- Article 14 reporting: actively exploited vulnerabilities and severe incidents, informing users. Applies from **11.9.2026**.
- Importers (Art. 19), distributors (Art. 20), authorised representatives (Art. 18), stewards (Art. 24).

### 4.2 Classifications

`default`, `important_class_i`, `important_class_ii`, `critical`, from `core_functionality_category`.

### 4.3 Assessment routes

| route | allowed when |
| --- | --- |
| `module_a_internal_control` | default; class I with `harmonised_standards_cover_core_functionality`; class I or II when FOSS (Art. 32(5)) |
| `module_b_c_type_examination` | any class |
| `module_h_full_quality_assurance` | any class |
| `eucc_certification` | where a delegated act under Art. 8(1) requires it for critical products; otherwise critical follows the class II routes |

The Art. 8(1) and Art. 32 conditions need checking against the OJ text when encoded.

### 4.4 Findings (examples)

- Info: reporting obligations already apply (since 11.9.2026), regardless of placement date.
- Action required: class I without full harmonised-standard coverage → third-party assessment.
- Action required or caution: support period (3.4).
- Action required: substantial modification in this release (3.5).
- Caution: unfinished software release (Art. 4(3)): only for the time needed for testing, with a visible notice.
- Caution: preview (beta) features in a normal release. Our reading, to be checked in the legal review, since the guidance doesn't address it: Art. 4(3) covers unfinished *software* made available for testing (alpha/beta/RC builds), not a feature labelled beta inside a product that is placed on the market. That product is placed as a whole, so the beta feature must be in its risk assessment and meet the essential requirements like any other. Two ways that still work:
  - Ship the beta feature in a separate test build, distributed only to testers, for a limited time and with the warning. That build is then the unfinished software.
  - Ship it disabled, with its risks already assessed. Enabling it later is then not a substantial modification (Example 43). Disabled code is still attack surface (capability vs enablement).
- Caution: hardware capability present but disabled (e.g. debug port) → attack surface if enabled later.
- Info: legacy design (G 2.7); prior type-examination certificate (G 9.3.2).
- Caution: monetisation changes FOSS scope.

### 4.5 Fixtures from guidance examples

Turn the guidance's worked examples into package fixtures, so each outcome traces to a numbered example: placing on the market (Examples 1–2), web app vs installed client (3–6), printer and drivers (8), FOSS (13–26), spare parts (36–39), substantial modification (40–50), support period (54–56), core functionality (57–61), RDPS use cases (G 8.3). That needs fixtures to assert classifications and routes too (6.5).

## 5. Shared questions with IEC 62443 and NIST SSDF

Full research: [`eu-cra-standards-overlap.md`](eu-cra-standards-overlap.md) (candidate questions with references, a CRA Annex I ↔ 62443-4-1/4-2 ↔ SSDF crosswalk for evidence reuse, spec-specific facts, pitfalls). WebFetch was blocked, so most requirement ids there are from memory and marked †; the crosswalk must be checked against the ENISA/JRC "CRA Requirements Standards Mapping" (2024) before use.

**The overlap splits in two.**

- **Process facts overlap across all three** (CRA Part II and Art. 13, 62443-4-1, SSDF): `documented_secure_development_process`, `performs_cybersecurity_risk_assessment`, `performs_threat_modelling`, `scans_for_known_vulnerabilities`, `security_testing_before_release`, `penetration_testing_performed`, `blocks_release_with_known_exploitable_vulnerabilities`, `third_party_component_due_diligence`, `sbom_scope` (choice: none · top-level · full transitive), `protects_development_environment`, `signs_releases`, `monitors_component_vulnerabilities`, `has_cvd_policy`, `has_vulnerability_contact`, `vulnerability_remediation_process`, `publishes_security_advisories`, `provides_secure_use_documentation`. Two-way (62443-4-1 + SSDF): security roles and training, documented security requirements, design review, secure coding standard, code review or static analysis.
- **Product facts overlap almost only between CRA Part I and 62443-4-2.** SSDF is process-only and touches products only through secure defaults (PW.9) and release integrity (PS.2). Candidates: `network_interface_capability`, `wireless_interface_capability`, `physical_debug_interface` (hardware capability choices: not present · present · present but disabled), `inbound_exposure_default` and `inbound_exposure_max` (none · same device only · restricted by the product itself · any network; an operator's VPN or firewall is a separate deployment-assumption question, `relies_on_network_isolation`), `requires_user_authentication`, `default_credentials` (choice incl. "same default on every unit"), the existing MFA trio, `role_based_access_control`, `encrypts_data_in_transit`, `sensitive_data_at_rest`, `update_mechanism` (choice: none · manual · automatic on/off by default), `verifies_update_authenticity`, secure boot (split into hardware root of trust + software enablement, per capability vs enablement), `minimal_default_configuration`, `supports_reset_to_defaults` and `data_erasure_method` (none · logical delete, possibly recoverable · secure erase; CRA I.2(m) asks for permanent removal, so a reset alone or a logical delete falls short), `security_event_logging`, `dos_resilience_measures`, `includes_third_party_components`.
- **Also common, though CRA-only among these three**, because RED, MDR, LVD and GDPR packages will reuse them: the scope exclusions, `economic_operator_role`, `is_free_and_open_source`, `is_commercial_activity`, `processes_personal_data` (data minimisation, GDPR).

**`implied_by` rules (strict implications only):** `uses_mfa` ⇐ either MFA requirement; `requires_user_authentication` ⇐ `uses_mfa`; `has_data_connection` ⇐ an interface present or `inbound_exposure_max` not "none" (derive true only, never false); `security_testing_before_release` ⇐ `penetration_testing_performed`; `signs_releases` ⇐ `verifies_update_authenticity`. Not: risk assessment ⇐ threat model, due diligence ⇐ SBOM, secure defaults ⇐ no listening services. Derivation across levels works (resolution gathers all levels of a configuration before deriving).

**CRA-specific refinements** sit in `eu-cra` with a `condition` on the common question, so shared labels stay neutral: automatic updates on by default with opt-out, logging opt-out, free security updates, security fixes separate from features, support period, Art. 14 reporting readiness. The same fact is judged differently: OT practice under 62443 has the operator apply patches, the CRA wants automatic updates by default. So `common` labels must not carry a judgement; packages raise the findings.

**Constraints this surfaced:**

- `choice` is single-valued and comparisons are number-only. Ordinal facts (62443 security level 1–4, 4-1 maturity level) must be `number`; multi-valued facts (which interfaces, which 62443 component types) need one question each.
- Levels of library questions must be right before `common` 1.1.0 is approved: the linter rejects the same id at a different level, so changing a level later is breaking.
- The demo's `has_wireless` (boolean) is the same fact as `wireless_interface_capability` (choice). Use the new id; leave or migrate the demo.
- Same words, different meanings: "component", "risk assessment", "secure by default", "SBOM" vs runtime inventory (62443-4-2 component inventory is not an SBOM).
- Process answers are self-attested; each should link to evidence (ADR 0011), with the crosswalk as the reuse key.
- 62443 and SSDF are not market-bound: they are selected per product (customer requirement, or harmonised standard once EN IEC 62443-4-1/A11 and 4-2/A11 are cited), not activated by target market.

## 6. Engine and schema changes (each needs an ADR; next free number 0018)

1. **Requirement `applies_when`, and `applies_from`/`applies_until` with a basis** (`placement` or `assessment`), also at package level (4.1.1). Requirements outside their dates are shown with them, not hidden. The staleness job flags approved assessments when an assessment-based date they depend on passes.
2. **Role-aware evaluation.** Filter requirements by `economic_operator_role`; add `authorised_representative` and `steward` to the roles enum.
3. **Target markets on software too** (decision 7.1).
4. **No copy-forward for per-release questions.** A question flag such as `carry_forward: false`, so release deltas start unanswered.
5. **Fixture expectations for classifications and routes,** not just `in_scope` and findings.
6. **Choice values with id and label** (optional). Annex III names are long and may be corrected later; ids keep answers stable.
7. **Requirement status in assessments:** met, not applicable (justified), compensating measures, open. G 2.6 and recital 55 make "not applicable, justified" a normal outcome. Likely shared with the Evidence milestone.
8. **Date question type.** Placement dates and the support end date (3.1, 3.4), with date comparisons and a years-between operator in the rule engine. Reusable: every product law has its own application date, so one placement date per level beats a "placed before X?" boolean per regulation.

## 7. Decisions and open questions

Decided in review (2.10.2026):

1. **Target markets on software releases too,** not only on HW variants. A software-only product sets its markets on the release. Proposal for configurations that have both: the effective markets are the intersection (a configuration is sold where both its hardware and its release are), and a release without markets inherits the HW variant's. Resolves the software-only open question in `docs/architecture.md`; needs an ADR.
2. **Process answers per product,** not per organisation or family (3.7).
3. **Placement dates on both HW revisions and SW releases** (3.1), as dates, not booleans (6.8).
4. **Full official Annex III/IV category names,** with attribution in the User Guide (3.3).
5. **`eu-cra` replaces the scaffold package;** no coexistence or withdrawal before version 1.0 (1).
6. **All economic operator roles from the start** (4.1).
7. **National security, defence and classified information are three separate questions** in `common` (3.1).

Still open:

1. **Effective markets rule** for configurations with both hardware and a release: intersection, as proposed above?
2. **Harmonised standards.** None cited in the OJ yet; the question stays generic until they are. Track the CEN/CENELEC/ETSI work (EN 40000 series, EN IEC 62443-4-1/4-2 A11) for later `harmonised_standard` packages, which is where cessation dates (4.1.1) will first matter.
3. **Legal review list:** category names against the OJ text, Art. 8(1)/32 routes, all `ref` citations, and our reading of preview features (4.4).

## 8. Phasing (proposed)

0. ADRs for section 6 and decision 7.1 (next free number 0018; `docs/adr/` has duplicate 0012 and 0015).
1. Engine changes 6.1–6.5 and 6.8, tested with the demo packages.
2. `packages/common` 1.1.0: shared questions from section 5, the scope exclusions, role and placement dates, and the FOSS/commercial questions.
3. `eu-cra` 1, replacing the scaffold package in the same change: scope, roles, classification, routes, support period, substantial modification; fixtures from guidance examples.
4. `eu-cra` 2: full requirements and findings (Annex I, Art. 13, 14, 18–20, 24) with the evidence crosswalk.
5. User Guide (category attribution, how to answer), legal review against the OJ text.

Later, not part of this plan:

- **Compare assessments** side by side, per product, HW revision and SW release, e.g. what changed between two releases or two revisions.
- IEC 62443 and NIST SSDF packages, reusing the common questions (selected per product, not by market).
- Requirement status and evidence links per requirement (6.7) with the Evidence milestone.
