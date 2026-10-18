# 47. Radio equipment outside RED falls back to the LVD

Status: Accepted (not legally reviewed).

## Context

`eu-lvd` 1.0.0 excluded every product with a usable radio, because RED Art. 3(1)(a) applies the LVD safety objectives to radio equipment (ADR 0045). The exclusion tested only the radio, not whether RED applies. RED Art. 1(3) excludes radio equipment used exclusively for public security, defence and State security, so a mains-powered radio product for national security came out of both packages, with no electrical-safety obligations shown at all.

The LVD has no defence or security exclusion (Annex II does not list one). Its reason for stepping aside, that RED covers the safety objectives, does not hold when RED does not apply.

## Decisions

- **`eu-lvd` 1.1.0** (`2014-35@2026-10.1`, supersedes 1.0.0) excludes radio equipment only while RED covers it: a usable radio and neither `is_exclusively_defence_product` nor `is_exclusively_national_security_product`. Both are existing shared questions that `eu-red` already uses for its Art. 1(3) exclusion, so the two packages agree on the answer. A product never falls into both or neither.
- **A caution, `radio_outside_red_security`**, explains the fallback and that a Member State may set EU product rules aside for its essential security interests (Art. 346 TFEU), so national rules and procurement terms need checking.
- **RED's other exclusions are not mirrored.** For marine equipment and airborne products, other regimes cover safety, so whether LVD applies again is unclear and left as it is. Custom R&D evaluation kits are excluded by LVD Annex II anyway. Amateur radio kits are rare enough to wait for the legal review.

## Consequences

- A cross-package test covers national-security and defence radios (LVD carries the safety objectives, RED is out) next to the earlier cases.
- `eu-lvd` 1.0.0 stays for existing installs; approving 1.1.0 supersedes it.
- Legal review: whether the LVD applies to equipment exclusively for defence or security, how Art. 346 TFEU is used in practice, and the marine, airborne and amateur-radio cases.
