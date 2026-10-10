# 21. Per-release questions are not carried forward

Status: Accepted

## Context

A new software release copies answers forward as "needs confirmation" (ADR 0004). That suits facts that usually persist (the product encrypts traffic). It is wrong for facts about one release's change: "this release adds new interfaces" (the CRA substantial-modification test, guidance section 4.3) describes that release only. Copying it forward invites confirming yesterday's delta.

## Decision

A question may declare **`carry_forward: false`** (package and question-set schemas). `copy_answers_forward` skips release-level answers to such questions, so the new release starts with them unanswered. The flag is read from the approved question sets and requirement packages.

## Consequences

- Default stays `true`; existing questions are unaffected.
- Only answers attached to the release are affected; product- and hardware-level answers are inherited, not copied.
