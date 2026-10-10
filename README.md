# Aavistin

Open-source compliance and risk-assessment tool for product manufacturers.
See `docs/architecture.md` for the full design and `CLAUDE.md` for the
project's working agreements and milestones.

## Starting the system (local development)

Requires Docker or Podman with Compose support.

```bash
docker compose up --build
# or
podman compose up --build
```

This starts four services: `db` (PostgreSQL), `web` (Django dev server on
`localhost:8000`), `worker` and `scheduler` (background jobs — see
`docs/adr/0007-background-job-backend.md`). Each of `web`, `worker` and
`scheduler` first bootstraps a local `.env` from `.env.example` with a
random `DJANGO_SECRET_KEY`, if one doesn't already exist (see
`scripts/generate_env.sh`; a no-op once `.env` exists). `web` runs
migrations and seeds the default dev accounts below on every startup,
before starting the dev server.

Once it's up:

- App: http://localhost:8000/
- Django admin: http://localhost:8000/admin/
- Login: http://localhost:8000/accounts/login/

## Default dev accounts

| Username   | Password   | Role                    |
|------------|------------|-------------------------|
| `admin`    | `admin`    | Superuser (admin site)  |
| `aavistin` | `aavistin` | Regular (non-staff) user|

These are seeded by `python manage.py seed_dev_users`
(`apps/accounts/management/commands/seed_dev_users.py`), which the `web`
service runs automatically on startup. They are for local development
only — the command is idempotent (safe to re-run, resets the passwords
each time) and must never be run against a non-dev database. Nothing
seeds these accounts outside of `docker-compose.yml`'s dev commands.

## Default groups, organisation and roles

`python manage.py seed_dev_roles`
(`apps/orgs/management/commands/seed_dev_roles.py`), also run automatically
by the `web` service on startup right after `seed_dev_users`, seeds:

- One `django.contrib.auth.Group` per role in `apps.orgs.models.Role`
  (Viewer, Editor, Approver, Content curator, Organisation admin) —
  scaffolding for granting roles in bulk via Django admin, whatever the
  organisation.
- A **Default Organisation** / **Default Family** (`apps.orgs.models`),
  so there's somewhere to actually create a product.
- The `aavistin` dev user is added to the Editor and Approver groups,
  both granted at Default Organisation scope — enough to add, edit,
  approve and (while unapproved) delete a product and everything beneath
  it (hardware variants/revisions, software releases/options,
  configurations) from `/products/`, without needing Django admin at
  all. See `docs/adr/0008-product-level-authoring-and-approval-deferred.md`.

Same caveats as `seed_dev_users`: local development only, idempotent,
never run against a non-dev database.

## Packages

Regulation and other requirement content (EU CRA, RED, LVD, GDPR, and
non-legal sources like internal QMS procedures) lives outside application
code as versioned, schema-validated JSON **packages** under `packages/`
(see `docs/architecture.md`, "Requirement sources") — adding or changing a
regulation means writing a package, never changing Python code. The same
mechanism also covers risk-assessment method and catalog packages
(`docs/architecture.md`, "Risk assessment: methods and catalogs").

Nothing imports a package automatically — not even the demo ones — so a
fresh dev database has none installed. To add one, run these *inside* the
`web` container (not your host — it needs the app's dependencies and the
`db` container's `DATABASE_URL`; use `exec` if the stack is already up
via `docker compose up`, or `run --rm` otherwise):

```bash
docker compose exec web python manage.py import_package packages/eu-cra/1.0.0.json --kind requirement --official
```

This validates the file against the package JSON Schema, runs the
semantic linter, and runs the package's own test fixtures — it does
**not** activate it. Review the resulting lint/fixture report and diff
against the previous version in Django admin
(`/admin/packages/requirementpackage/`), then publish it with the
"Approve selected packages" admin action (or
`docker compose exec web python manage.py approve_package <source> <version>`).
Only approved packages affect real assessments.

## Running tests and lint

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests require a running PostgreSQL instance (see `DATABASE_URL` in `.env`
or `docker-compose.yml`) — this project never relies on SQLite.

### End-to-end (browser) tests

The tests under `e2e/` drive the real UI in Chromium via Playwright. They
are marked `e2e` and skipped by the default `pytest` run:

```bash
uv run playwright install chromium   # once
uv run pytest -m e2e
```

On failure, add `--screenshot only-on-failure --tracing retain-on-failure`
to keep artefacts under `test-results/`. If a Chromium is already installed,
point `PLAYWRIGHT_CHROMIUM_EXECUTABLE` at it instead of running the install.
