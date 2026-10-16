# 42. RED Art. 3(1)(a) safety objectives and shared safety questions

Status: Accepted (content is not legally reviewed).

## Context

`eu-lvd` excludes radio equipment, because RED Art. 3(1)(a) applies the LVD safety objectives to it without the voltage limits (ADR 0045). Both packages use the same radio test, so exactly one of them covers a product's electrical safety. But `eu-red` 1.0.0 had a single Art. 3(1)(a) requirement that only pointed to the LVD, and none of the LVD's safety and marking questions. A mains-powered Wi-Fi device lost those checks when it moved from LVD to RED, although the legal duty is the same. This came up while debugging why a demo product with a radio and a 220 V input was out of LVD scope.

## Decisions

- **`eu-red` 1.1.0** (`2014-53@2026-10.1`, supersedes 1.0.0) replaces `art_3_1_a_health_and_safety` with `art_3_1_a_health_protection` (health, for example radio-frequency exposure, which goes beyond the LVD) and eight requirements that mirror LVD Annex I(1) to I(3)(c). Each `ref` names RED Art. 3(1)(a) and the LVD Annex I point. Labels are our own summaries. LVD Art. 3 good engineering practice and Art. 6 documentation duties are not copied: RED Art. 10, 18 to 21 already cover documentation, declaration and CE marking.
- **Shared questions in `common` 1.4.0, under neutral ids:** `safety_risk_assessment_documented`, `technical_documentation_complete`, `electrical_ratings_marked`, `eu_declaration_of_conformity_drawn_up`, `ce_marking_affixed`, `product_identification_marked`, `safety_instructions_in_local_languages`, `supplier_conformity_checked`. They replace the `lvd_*` questions in `eu-lvd` 1.0.0, which is renamed in place because it had not been released. Neutral ids fit any CE-marking act, so EMC or RoHS packages can reuse them (`eu-emc` does, ADR 0047). Their conditions use only shared facts (hardware product form, role).
- **`lvd_conformity_basis` stays in `eu-lvd`.** Its choices (international and national standards, Art. 13 and 14) exist only in the LVD. RED has its own harmonised-standard questions.
- **Gap findings fire only in the package that covers the product.** A "no" answer is shared, so each package gates its finding with its own scope expression. A product never gets the same action twice.

## Consequences

- Fixtures and a cross-package test show exactly one package carrying the safety objectives: a mains Wi-Fi device under RED, a mains device without radio under LVD, and a radio that only a manufacturer update can enable under LVD with the caution.
- `eu-red` 1.0.0 stays in the repository for existing installs. Approving 1.1.0 supersedes it, and approved assessments become stale as for any package version change.
- Legal review: the Annex I mapping under RED, the health-protection summary, and the RED article numbers in the new findings (Art. 10(6) to (9), 12, 13, 18 to 21, Annex V).
