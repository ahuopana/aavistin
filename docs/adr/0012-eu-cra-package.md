# 12. EU CRA package: scope, and a linter gap it surfaced

Status: Accepted (content is a first pass, not legally reviewed -- see "Consequences")

## Context

`packages/eu-cra/1.0.0.json` is the first real (non-demo) requirement package: the EU Cyber Resilience Act, Regulation (EU) 2024/2847. `docs/architecture.md`'s demo seed section already specifies the exact expected behaviour for a fictional Aavistin-as-a-product scenario (Community release out of scope as free/open-source software outside a commercial activity; Paid support in scope, default category, internal control route; a caution finding when monetisation would change scope) — that's the acceptance spec this package's fixtures implement.

Building it surfaced a real gap in `apps/packages/linting.py`: `apps.assessments.evaluation.evaluate_configuration` injects `class__<classification_id>` synthetic variables into `finding_rules`/`assessment_routes` evaluation (so a route or finding can be gated on "is this product classified as X"), but the semantic linter's `_referenced_vars` check had no notion of this — it would flag `{"var": "class__default"}` as `unknown_question`, since no package had ever actually used the pattern before.

## Decisions

- **Linter fix**: `lint_package` now recognises `class__<id>` as valid when `id` matches a declared classification and the expression is in `assessment_routes[].allowed_when` or `finding_rules[].when` (the two places `evaluate_configuration` actually provides `class__` vars) — a real bug fix needed to import any classification-gated package at all, not new scope invented for this ADR.
- **`important`/`critical` classification is self-declared, not derived.** CRA Annex III (important products) and Annex IV (critical products) list specific product categories in detail. Rather than reproduce that list from memory — with a real risk of getting it subtly wrong in a compliance tool — this package asks the user two direct boolean questions ("does your product fall into an Annex III/IV category? judge for yourself") and classifies from the answer. Deriving the classification from concrete product facts is a documented follow-up, once the category list is verified against the current consolidated text.
- **Legal references are best-effort, not verified citations.** `ref` fields (e.g. "Recital 18 / Art. 2(4)") are written from general knowledge of the regulation's structure, explicitly marked in the package and its README as needing verification. This matches the plan stated before starting this work: flag interpretive/legal judgment calls for review rather than assert them confidently.
- **Requirements are representative, not exhaustive.** Six Annex I Part I/II obligations are included (secure-by-default, no known exploitable vulnerabilities at placing-on-market, vulnerability handling process, SBOM, timely security updates, incident/vulnerability reporting) rather than the full annex, per the "scope the first version narrowly" plan.
- **Single application date, not phased.** CRA's reporting obligations (Article 14) apply earlier than the main obligations; `dates_of_application` only supports one `from`/`until` pair, so this version uses the main application date (2027-12-11) and doesn't model the earlier reporting-only phase. A schema change would be needed to do better.

## Consequences

- **This package is not a substitute for legal advice**, and isn't a settled reading of the regulation — `packages/eu-cra/README.md` says so explicitly, and this ADR is where the specific things to verify are listed, so a legal review has a concrete checklist rather than needing to re-derive it: the `ref` citations, the Annex III/IV category list (once encoded), and the full Annex I requirement set.
- The `class__` linter fix is a small, generally-useful capability, not eu-cra-specific: any future package with classification-gated routes or findings benefits from it.
- Fixtures only cover `in_scope`/`findings` (what `apps.packages.fixtures_runner` checks); classification and assessment-route behaviour for this package is covered by an integration test against `apps.assessments.evaluation.evaluate_configuration` instead, in `apps/packages/tests.py`.
