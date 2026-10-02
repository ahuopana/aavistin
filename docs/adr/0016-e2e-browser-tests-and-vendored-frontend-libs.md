# 16. End-to-end browser tests and vendored front-end libraries

Status: Accepted

## Context

All existing tests are unit, module or Django test-client tests. None runs
JavaScript, so Alpine-driven behaviour (edit toggles, conditional fields)
and whole user journeys across several pages are untested. Not covered by
`docs/architecture.md`; CLAUDE.md asks for an ADR before adding tooling.

## Decision

- Add `pytest-playwright` (dev dependency only) and a first journey test in
  `e2e/`: editor builds a product, configuration and answers; a different
  user approves the assessment; an answer change makes it stale.
- Tests carry the `e2e` marker and are excluded from the default run
  (`addopts` has `-m "not e2e"`); CI runs them as a separate `e2e` job so
  the fast unit job is unaffected. No Node build is introduced.
- The tests are hermetic: requests to anything other than the live server
  (e.g. Google Fonts) are aborted.
- Alpine.js and htmx are vendored under `static/vendor/` at pinned versions
  (previously loaded from unpkg, with Alpine on a floating `3.x.x`), so the
  app and the tests do not depend on a public CDN being reachable.
  Google Fonts remain external (separate decision).
- Live-server tests flush the database on teardown, which removes the
  target markets seeded by a migration; a session fixture restores them so
  a reused test database stays valid.

## Consequences

- Contributors need `playwright install chromium` to run `-m e2e`.
- Upgrading Alpine or htmx is now a deliberate file replacement
  (see `static/vendor/README.md`).
- Further journeys (risk register, evidence) can reuse `e2e/conftest.py`.
