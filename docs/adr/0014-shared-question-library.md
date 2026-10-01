# 14. Shared question library and derived answers

Status: Accepted

## Context

`docs/architecture.md` says questions are shared across packages. In code
that held only by accident: answers are keyed by `question_id`, so two
packages declaring the same id read one answer, but each package
redeclared the question's type, level and label (they could drift), the
same fact under two ids was asked twice, and closely related questions
(MFA for all users vs. for administrators) could not inform each other.

## Decision

- **`question_set` package kind** (`schemas/question-set.schema.json`,
  `packages/common/`): canonical question definitions, versioned,
  linted, fixture-tested and approved like any package. Question ids are
  unique across sets.
- **`uses`** in a requirement package (`"common:uses_mfa"`) references a
  library question instead of redeclaring it. At resolution time
  (`package_questions`) library definitions come from the newest
  approved version of each set; each question records `used_by`, shown in
  the questionnaire as "also used by". Packages that still declare their
  own questions keep working (first-seen wins).
- **Linter:** error for an unknown `uses` reference, for a same-id
  question with a different type or level (in the library or another
  requirement package), for duplicate ids across sets, for unknown
  variables in `implied_by`, and for `implied_by` cycles; warning when a
  package redeclares a library question.
- **`implied_by: {when, value}`** derives a value when no explicit answer
  exists, using the safe rule engine. It chains to a fixpoint. An explicit
  answer at any level always wins; the UI labels the origin "derived".
  Used sparingly, where one answer clearly covers another.

## Consequences

- Approved assessments freeze resolved answers, so library edits never
  alter them. A library change alone does not mark an assessment stale;
  it takes effect when answers or package versions change. Recording
  question-set versions in the snapshot is a possible follow-up.
- Overriding a derived value does not require a justification: answers
  are not bound to a configuration, so `Answer.clean` cannot know what
  would have been derived. Deferred.
- Existing duplicated demo questions were not migrated; they still lint
  clean (identical definitions).
