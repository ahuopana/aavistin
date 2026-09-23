# 3. Hand-rolled JSONLogic-subset interpreter instead of a JSONLogic library

Status: Accepted

## Context

`docs/architecture.md` says rule expressions are "declarative expressions
(JSONLogic or a small custom language) evaluated safely, never Python
`eval`." CLAUDE.md repeats this as a hard rule. It doesn't mandate a
specific JSONLogic package.

Existing JSONLogic implementations for Python are small, lightly
maintained packages. Vetting one's internals for "never eval/exec" on
every dependency bump is ongoing work, and the operator set requirement
packages actually need (from `docs/architecture.md`'s own example and
the question/scope/finding-rule model) is small: `var`, `and`, `or`,
`!`, `if`, `in`, comparisons, and basic arithmetic.

## Decision

`apps/packages/ruleengine.py` is a small, hand-written interpreter: a
fixed dict of allowed operators, each a plain Python function operating
only on already-evaluated values. There is no `eval`, `exec`, attribute
access, or lookup into anything but that dict and the answers dict
passed in. Unknown operators, non-object expressions, wrong argument
counts, and numeric operators applied to non-numbers all raise
`RuleEngineError` rather than doing something surprising.

## Consequences

- The whole "never eval/exec" surface is ~150 lines we wrote and can
  audit directly, rather than a transitive dependency.
- Adding an operator (e.g. more string ops, if a package needs one) is a
  one-function, one-dict-entry change, reviewed like any other code
  change.
- The trade-off is not implementing full JSONLogic (no `map`/`reduce`/
  `merge`/custom-op registration). That's intentional: requirement
  package rules are boolean scope/finding conditions over question
  answers, not general computation, so the smaller surface is a feature,
  not a gap. If a package genuinely needs an operator this doesn't have,
  extend the whitelist rather than switching interpreters.
