# 22. The full `eu-cra` package replaces the scaffold

Status: Accepted. Supersedes the addendum of ADR 0012.

## Context

ADR 0012's addendum renamed the first CRA package to `eu-cra-partial` and expected it to live on beside a later full package, so references to it would keep their meaning. Aavistin has no real users before version 1.0, so nothing references it outside this repository.

## Decision

- `packages/eu-cra` (source `eu-cra`) is the full package, built to `docs/plans/eu-cra-full.md`. `packages/eu-cra-partial` is deleted in the same change, with its tests moved to `eu-cra`. No coexistence or withdrawal mechanism is built.
- Shared facts live in `packages/common` 1.1.0 and are referenced with `uses`. Only CRA-specific questions (core-functionality category, remote data processing, spare parts, support period, substantial-modification tests) are declared in the package.
- The core-functionality question uses the official Annex III/IV category names, prefixed with their annex and number; the attribution is in the User Guide.
- Fixtures reproduce the Commission guidance's numbered examples where they translate into answers, so each outcome traces to the guidance.

## Consequences

- The removed self-declared booleans (`is_annex_iii_important_product`, `is_annex_iii_critical_product`) are replaced by one category choice; there are no stored answers to migrate.
- The legal-review list in the plan applies to this package before it backs a real compliance decision.
