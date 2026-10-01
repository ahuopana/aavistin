# eu-cra

The first real (non-demo) requirement package: the EU Cyber Resilience
Act, Regulation (EU) 2024/2847 (CELEX `32024R2847`).

**This is a first pass, not a legally reviewed compliance artifact.**
Scope logic, classifications and the finding rule match the behaviour
already documented and agreed in `docs/architecture.md`'s demo seed
section. Everything else — the exact legal references (`ref` fields),
the Annex I requirement list, and the assessment-route mapping — is a
best-effort structural sketch written from general knowledge of the
regulation, not verified against the current consolidated legal text.
See `docs/adr/0012-eu-cra-package.md` for exactly what was assumed and
what needs checking before this package backs a real compliance
decision.

## What this version covers

- **Scope**: in scope by default; excluded when free-and-open-source
  *and* supplied outside a commercial activity (matches the demo
  seed's Community release / Paid support example exactly).
- **Classifications**: `default`, `important`, `critical`. Whether a
  product falls into `important` or `critical` is a question the user
  answers themselves (against Annex III/IV) — this package does not
  reproduce that category list, to avoid asserting a possibly
  inaccurate enumeration from memory. Each self-assessed question
  (FOSS status, commercial activity, Annex III/IV) carries a
  `guidance` field — our own summary of how to approach that
  self-assessment (e.g. the "core functionality" test), shown in the
  UI as a "Good to understand before you answer" note — plus a
  `guidance_url` to the European Commission's CRA guidance document for
  further reading.
- **Requirements**: a representative, non-exhaustive set of Annex I
  Part I (product) and Part II (vulnerability handling) obligations —
  secure-by-default, no known exploitable vulnerabilities at
  placing-on-market, a vulnerability handling process, an SBOM, timely
  security updates, and incident/vulnerability reporting.
- **Assessment routes**: `internal_control` for the default category,
  `third_party_assessment` for `important`/`critical` — the exact
  conformity assessment module (Annex VIII) isn't selected.
- **Finding rules**: the demo seed's monetisation-changes-scope
  caution, plus an action-required finding when a product is
  `important`/`critical` (third-party assessment needed).

## What's deferred

- The actual Annex III/IV category lists (so `important`/`critical`
  can be derived from concrete product facts instead of self-declared).
- Phased application dates (Article 14 reporting obligations apply
  earlier than the main obligations; the schema only supports one
  `from` date).
- The rest of Annex I's requirements, and exact Annex VIII module
  selection.

## Importing

Run inside the `web` container (see the main `README.md`'s "Packages"
section for why). The file is named `1.0.0.json` for convenience, but
the package's own `version` field — what `approve_package` and every
other lookup actually key on — is `2024-2847@2026-09`, not `1.0.0`:

```bash
docker compose exec web python manage.py import_package packages/eu-cra/1.0.0.json --kind requirement --official
```

Review the lint/fixture report this prints (and the diff/report in
Django admin) before approving — per the caveats above, this package
hasn't been checked against the current consolidated legal text, so
don't publish it as-is against a real compliance decision:

```bash
docker compose exec web python manage.py approve_package eu-cra "2024-2847@2026-09"
```
