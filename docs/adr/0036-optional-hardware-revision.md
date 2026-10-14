# 36. A configuration's hardware revision is optional

Status: Accepted

## Context

ADR 0020 let a software release carry target markets, but a configuration still required a hardware revision, so software-only products (Aavistin itself, an app, a cloud service) needed a nominal hardware entry.

## Decisions

- `Configuration.hardware_revision` is nullable. The software release stays required, so a configuration always belongs to a product through it.
- `Configuration.product` (via the release) replaces the `hardware_revision.hardware_variant.product` chain everywhere; `Configuration.hardware_variant` is `None` for software-only setups.
- Effective markets of a software-only configuration are the release's markets (ADR 0020 already defined this for "only one set").
- Questions whose `level` is `hardware` are not asked when the configuration has no hardware: there is nothing to attach the answer to. Product, software and option questions work as before. Conditions that depend on a hardware answer see it as unanswered.
- Risk entries scoped to a hardware variant do not apply to a software-only configuration; baseline entries and release/option scopes do.
- Readiness explains the case "no hardware and the release has no markets".

## Consequences

- Existing data is unchanged; the migration only drops `NOT NULL`.
- A hardware-only configuration (no release) is still not supported.
