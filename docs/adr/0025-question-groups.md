# 25. Question groups in requirement packages

Status: Accepted.

## Context

The questionnaire sorted questions by id, so topics were interleaved (an update question next to a scope exclusion). Shared questions live in `packages/common` and are reused by several packages, so putting a topic on the question itself would force every regulation into one grouping and change `common` for each edit.

## Decision

- A requirement package may declare an ordered `question_groups` list: `{id, title, questions[]}`. It can list questions the package declares and ones it takes with `uses`. Order in the list is display order.
- Grouping is presentation per regulation, so `common` is unchanged. If several active packages group the same question, the first one wins.
- The linter errors on unknown question ids, a question in two groups and duplicate group ids, and warns about questions left out of every group. Ungrouped questions are shown last under "Other questions". With no groups the questionnaire is unchanged (sorted by id, no headings).
- `eu-cra` follows the Act's own structure: scope and exclusions (Art. 2), classification (Annex III/IV), security by design (Annex I Part I), vulnerability handling (Annex I Part II, split into before release and after release), and updates.
