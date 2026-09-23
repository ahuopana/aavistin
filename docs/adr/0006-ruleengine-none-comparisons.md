# 6. Numeric comparisons treat an unanswered question (None) as false

Status: Accepted

## Context

Milestone 6's catalog triggers (`apps/packages/catalog_engine.py`) and
suggestion flow (`apps/risk/suggestions.py`) call
`apps.assessments.evaluation.evaluate_configuration`, which evaluates
every active package's classification `when` expressions — including
before any questions have been answered (e.g. `pending_suggestions`
runs against whatever's been answered so far, which can be nothing). A
resolved-but-unanswered question's value is `None`
(`apps/assessments/resolution.py`, `ResolvedAnswer.value`).

Before this milestone, every caller of the rule engine (fixtures,
already-complete assessments) always evaluated against a fully-answered
data set, so a numeric comparison like `{">": [{"var":
"rated_power_watts"}, 80]}` never saw `None` for `rated_power_watts` in
practice. `apps/risk/tests.py::SuggestionTests::test_no_suggestions_without_matching_context`
(calling `pending_suggestions` with zero answers recorded) hit exactly
this path and raised `RuleEngineError: expected a number, got None`.

## Decision

`apps/packages/ruleengine.py` splits the old single `_numeric_binary`
into `_comparison` (`<`, `<=`, `>`, `>=`) and `_arithmetic` (`+`, `-`,
`*`, `/`). Comparisons treat either operand being `None` as the
comparison being false — "rated_power_watts > 80" is simply not yet true
when the question hasn't been answered, the same way a boolean var
defaults to falsy when unanswered. Arithmetic operators are unchanged:
`None` still raises, since there's no sensible numeric result for
`None + 1`.

## Consequences

- `evaluate_configuration` (and anything built on it — catalog triggers,
  the questionnaire's own classification/finding evaluation) no longer
  crashes when called with partial or no answers; a numeric-gated
  classification or finding just doesn't fire yet.
- This is a behavioural change to code shipped in Milestone 4/5, though a
  narrow one: lint and fixture semantics are unaffected (a fixture still
  provides a full answer set; no existing fixture relied on the old
  raise-on-None behaviour). Covered by
  `apps/packages/tests.py::RuleEngineTests::test_comparison_with_unanswered_question_is_false_not_an_error`
  and `test_arithmetic_with_none_still_raises`.
