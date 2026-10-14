# 38. Generic compare of two entities

Status: Accepted

## Context

Reviewers need to see what differs between two similar things: two software releases, two hardware revisions, two configurations (what a firmware update changes in scope), two assessments (what changed since the approved one), or even two products. Only package imports had a diff (`apps/packages/diffing.py`).

## Decisions

- **One page, one kind at a time.** `/compare/?kind=&a=&b=` takes two entities of the same kind: product, hardware variant, hardware revision, software release, software option, configuration, assessment. Mixing kinds is not offered, because their facts do not line up.
- **Subjects and sections.** Each entity is reduced to named sections of `row label -> text` (`apps/core/compare.py`): details, structure, answers set on that entity, and for configurations and assessments the evaluation (packages and scope, requirements in force, findings, resolved answers with their origin) and the risk register. A generic diff marks rows same, changed, or only in A or B. The comparison is therefore as regulation-agnostic as the evaluation itself; labels come from package content.
- **Assessments** use the frozen snapshot when approved, else a live evaluation, so "approved vs now" and "approved vs approved" both work.
- **Visibility.** Only entities under products on which the user holds any role are offered and accepted; a guessed id outside that set is treated as "not chosen".
- **Cross-product comparison is allowed** for anything the user can see (two similar products, hardware of different products).
- Read-only: no new tables or migrations.

## Consequences

- Rows are text, so structured values (lists, nested objects) are flattened; a row-level "changed" shows both texts side by side rather than a character diff.
- Evidence and risk ratings are not compared yet; entries are compared by type and label only.
