# 48. Voltage ratings move to the shared question library

Status: Accepted.

## Context

`eu-lvd` declared `ac_voltage_rating` and `dc_voltage_rating` itself (ADR 0045). The planned `eu-rohs` package needs the same two facts: RoHS covers electrical and electronic equipment rated up to 1000 V AC or 1500 V DC (Directive 2011/65/EU, Art. 3(1)), so a product assessed under both would be asked twice, and two separate questions could be answered differently. `docs/plans/eu-rohs.md` proposed moving them; the decision is confirmed.

## Decisions

- **`common` 1.5.0** (supersedes nothing; 1.4.0 stays for existing installs) adds `ac_voltage_rating` and `dc_voltage_rating`, with the same ids, type (number, V), level (hardware), label and guidance as in `eu-lvd` 1.1.0.
- **`eu-lvd` 1.2.0** (`2014-35@2026-10.2`, supersedes 1.1.0) lists them under `uses` and no longer declares them. Scope, requirements, findings and fixtures are unchanged, so an approved assessment gives the same result.
- **Older versions are not edited.** `eu-lvd` 1.0.0 and 1.1.0 still declare the questions themselves and are imported against `common` 1.4.0. Pairing them with 1.5.0 is not tested (the same ids would be declared twice); install `eu-lvd` 1.2.0 with `common` 1.5.0.
- **LVD and RED stay mutually exclusive** (ADR 0045, 0047). RoHS is independent of both and can apply alongside either; no fallback rules between RoHS and the other two.

## Consequences

- `eu-cra` and `eu-red` pass unchanged against `common` 1.5.0 (tests cover both 1.4.0 and 1.5.0).
- The package READMEs and the root README import `common` 1.5.0.
- Approving `eu-lvd` 1.2.0 marks assessments approved under 1.1.0 as stale for re-review, as for any new package version; their results do not change.
