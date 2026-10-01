# 14. Optional self-assessment guidance text on questions

Status: Accepted

## Context

`packages/eu-cra/1.0.0.json` (see ADR 0012) deliberately asks the user to self-declare Annex III/IV classification and FOSS/commercial-activity status, rather than reproduce those lists or tests from the regulation. The question labels alone ("judge this yourself") give no hint of *how* -- e.g. nothing points the user at the "core functionality" test (section 6.1 of the European Commission's CRA guidance) that actually drives the Annex III/IV call, or at the two-part FOSS definition. A user answering cold has to go find and read the guidance document themselves.

## Decision

Questions gain two optional fields, `guidance` and `guidance_url` (`schemas/package.schema.json`, `$defs.question`):

- `guidance` is **plain text**, not Markdown or HTML. It is rendered with Django's normal auto-escaping, so it needs no `nh3` sanitisation pass and no new rendering dependency -- consistent with "don't add abstractions beyond what the task requires". A short explanatory sentence or two is all the use case needs; nothing in the current packages calls for rich formatting.
- `guidance_url` is an optional link to the authoritative source, for anything longer than a sentence or two can usefully cover.
- The UI shows both, when present, under a collapsed `<details>` labelled "Good to understand before you answer", directly under the question label in `templates/assessments/configuration_detail.html`. Collapsed by default so it doesn't crowd the table for questions that don't need it.
- `packages/eu-cra/1.0.0.json`'s four self-assessed questions (`is_free_and_open_source`, `is_commercial_activity`, `is_annex_iii_important_product`, `is_annex_iii_critical_product`) now carry guidance: our own short summary of how to approach each self-assessment, plus a `guidance_url` to the Commission's CRA guidance document.

Like `ref` citations and requirement labels, `guidance` text is our own summary, never standards/legal text verbatim -- the same rule `CLAUDE.md` already states for the rest of a package's content.

## Consequences

- Purely additive to the schema (`additionalProperties: false` on `question` already required naming the new keys explicitly); existing packages and fixtures are unaffected, no migration needed.
- Because `guidance` is plain text, a package cannot link-format or emphasise inline -- only via the separate `guidance_url` "read more". If a future package genuinely needs richer formatting, that's a new decision (Markdown + `nh3`, a real new dependency), not an extension of this one.
- `guidance`/`guidance_url` are advisory UI content, not evaluated by the rule engine -- they carry no `ref` and never affect scope, classification, or findings.
