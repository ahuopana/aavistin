# 4. Answers attach to HardwareRevision, not HardwareVariant

Status: Accepted

## Context

`docs/architecture.md`'s "Answer inheritance" prose gives the precedence
chain as "option → SW release → HW variant → product," but its own
diagram groups "HW variant / revision" into a single node, and
`Configuration` (Milestone 3, built from the same doc) ties an assessment
to a specific `HardwareRevision`, not a `HardwareVariant`. A revision is
exactly the mechanism by which hardware capability changes between
board spins (a component added or removed), which is the same kind of
fact a hardware-level question records (per the "Capability vs
enablement" table). Treating "HW variant" in the prose as shorthand for
the diagram's combined node, rather than a fourth, separate level, keeps
one hardware-level answer store aligned with the one hardware entity
`Configuration` actually references.

## Decision

`Answer` attaches to exactly one of `Product`, `HardwareRevision`,
`SoftwareRelease` or `SoftwareOption`. Resolution precedence (most
specific first) is: `software_option` → `software_release` →
`hardware_revision` → `product` (`apps/assessments/resolution.py`,
`PRECEDENCE`). There is no separate `HardwareVariant`-level answer.

A second, smaller simplification: a `Configuration` can select several
`SoftwareOption`s at once, and the architecture doc doesn't say how an
option-level question resolves when more than one selected option has
its own answer. `resolve_answer` checks the configuration's selected
options in `id` order and takes the first one that has an answer for
that question. The web questionnaire UI (`apps/assessments/views.py`)
goes further and only exposes editing for the first selected option;
answering per-option directly (any option, any question) works through
the service layer and Django admin, exercised by
`apps/assessments/tests.py`, just not yet through the questionnaire
page.

## Consequences

- `resolve_answer`/`resolve_answers` implement one unambiguous chain
  that matches the actual Milestone 3 schema; no fifth level to keep in
  sync if `HardwareVariant` also grew its own answers later.
- The option-ordering rule (lowest id wins when several selected options
  answer the same question) is arbitrary but deterministic and
  documented here; if a real package ever needs different multi-option
  precedence, this is the place to change it.
- Multi-option questionnaire UI (letting an editor answer the same
  question differently per selected option, side by side) is deferred —
  a real gap for products that ship configurations with several
  simultaneous options, worth revisiting once there's a concrete package
  that needs it.
