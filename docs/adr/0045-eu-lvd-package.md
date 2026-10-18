# 45. EU LVD package

Status: Accepted (content is a first pass, not legally reviewed).

## Context

`docs/architecture.md` names the LVD (Directive 2014/35/EU) as a first target, and the demo seed expects it to be out of scope for software-only Aavistin. The directive is simpler than the CRA: one voltage-based scope rule, an exclusion list, no classes and a single conformity route. Several of its scope questions turn on interpretations from the Commission's LVD guidelines rather than the directive's text.

## Decisions

- **`packages/eu-lvd`, source `eu-lvd`, version `2014-35@2026-10`**, following the `eu-cra` and `eu-red` layout (shared questions via `uses`, question groups, role expression, per-role requirements, fixtures with `as_of`).
- **Scope from two voltage ratings.** AC and DC ratings are numbers at hardware level, in volts, for the product's inputs and outputs. In scope when either is in range (50–1000 V AC, 75–1500 V DC), or when either is unanswered (nothing hidden while unknown). Standalone software and software components are out.
- **`common` 1.3.0 adds the product form `hardware_without_software`** to 1.2.0. Most LVD products (kettles, extension leads, lamps) have no software, and the existing choices forced them into `hardware_with_software`. Adding a choice changes no CRA or RED outcome: CRA scope still turns on the data connection, RED scope on the radio.
- **Annex II as one choice**, with one scope exclusion per category. Medical and radiology equipment reuses the shared `is_medical_device` and `is_in_vitro_diagnostic` questions instead of a second question.
- **Two exclusions are interpretations, labelled as such in `ref`:** basic components whose safety depends on how they are built in (Commission LVD guidelines), and radio equipment, whose LVD safety objectives apply through RED Art. 3(1)(a) with no voltage limit. "Radio equipment" uses the same test as `eu-red`'s scope (ADR 0023), so exactly one of the two packages covers electrical safety: a radio that is physically disabled or enableable only by a manufacturer update leaves the product under LVD, with a caution that enabling it moves the product to RED.
- **One route, internal production control (module A).** The directive has no notified-body route.
- **No placement-date conditions on requirements.** All apply from 20 April 2016. Units placed earlier under 2006/95/EC (Art. 25) get an info finding only.
- **Documentation and marking gaps are self-assessed booleans** shown only to whoever acts as manufacturer (or to importers and distributors for the supplier check) and only while the product may be in scope. A "no" raises an action-required finding.

## Consequences

- `eu-cra`, `eu-red` and `eu-lvd` all pass with `common` 1.3.0; the `common` and `eu-lvd` READMEs import it.
- Addendum (ADR 0042): the documentation and marking questions moved to `common` 1.4.0 under neutral ids, and `eu-red` 1.1.0 breaks Art. 3(1)(a) down into the same safety objectives, so a radio product keeps the LVD-equivalent checks.
- Addendum (ADR 0047): `eu-lvd` 1.1.0 excludes radio equipment only while RED covers it; radio equipment that RED excludes for defence or security falls back to LVD.
- Machinery Regulation, EMC and RoHS interplay is not modelled; harmonised standards are not listed.
- The legal-review list for this package: the `ref` citations, the Annex II category wording, the two interpretive exclusions, and the requirement summaries against the Official Journal text.
