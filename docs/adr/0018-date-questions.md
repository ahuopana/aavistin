# 18. Date questions and date rules

Status: Accepted

## Context

Product law keys obligations to when a product was placed on the market (CRA: 11 December 2027; Art. 69(1) certificates until 11 June 2028) and to dates the manufacturer declares (CRA Art. 13(19): end of the support period). Questions could only be `boolean`, `choice` or `number`, and the rule engine compared numbers only. A "placed before 11.12.2027?" boolean per regulation would multiply and still not express "last units placed after a date". See `docs/plans/eu-cra-full.md`, 4.1.1.

## Decision

- **`date` question type** (both package and question-set schemas). Answers are ISO dates (`YYYY-MM-DD`) stored as strings. The questionnaire renders a date input.
- **Comparisons on dates.** `<`, `<=`, `>`, `>=` accept two ISO dates (an answer and a literal, or two answers) and compare them as dates. Mixing a date with a number is an error. An unanswered date still makes a comparison false, like an unanswered number.
- **`years_between`** `[start, end]` returns the number of complete calendar years from `start` to `end` (negative if `end` is earlier); `null` if either is unanswered. Complete years, not days / 365, so "five years from 2028-03-15" ends exactly on 2033-03-15.
- **Linter:** a date question may appear under a comparison or `years_between`, never under arithmetic; a number may not appear under `years_between`.
- **No "today" in expressions.** Rules stay deterministic and fixtures reproducible. Comparison with the assessment date happens outside expressions (ADR 0019).

## Consequences

- One placement date per level (`hardware_first_placed_on_market`, `software_first_placed_on_market` in `packages/common`) serves every regulation, each comparing against its own date.
- `Answer.value` is a JSON field, so no migration; existing answers are unaffected.
