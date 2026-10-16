# Development

Everything for working on Aavistin itself. For installing and running it, see the [README](../README.md). The design is in [`architecture.md`](architecture.md); decisions not covered there are recorded in [`adr/`](adr/). `CLAUDE.md` holds the working agreements and the milestone list.

## Running the stack locally

Requires Docker or Podman with Compose support.

```bash
docker compose up --build
# or
podman compose up --build
```

This starts four services:

| Service | What it does |
| --- | --- |
| `db` | PostgreSQL 16 |
| `web` | Django dev server (`runserver`) with the project mounted for live reload |
| `worker` | Background jobs from the Postgres-backed queue |
| `scheduler` | Enqueues the periodic jobs, such as the staleness refresh |

See `docs/adr/0007-background-job-backend.md` for the job design. Each of `web`, `worker` and `scheduler` first creates a local `.env` from `.env.example` with a random `DJANGO_SECRET_KEY`, if there is none (`scripts/generate_env.sh`; a no-op once `.env` exists). `web` then runs migrations and seeds the dev accounts and roles below, on every start.

Once it is up:

- App: <http://localhost:8000/>
- Django admin: <http://localhost:8000/admin/>
- Login: <http://localhost:8000/accounts/login/>

The host ports come from `WEB_PORT` and `DB_PORT` (read by Compose from `.env`). `.env.example` sets `WEB_PORT=8080`, so once the generated `.env` exists the app is on <http://localhost:8080/> instead; edit `.env` to change either port.

`docker-compose.yml` is for development only: it runs with `DEBUG` on, mounts the source over the image, publishes the database port and uses a fixed database password. Do not use it for a real deployment; see "Running in production" in the README.

### Without Docker

```bash
uv sync
cp .env.example .env        # then set DJANGO_SECRET_KEY and DATABASE_URL
uv run python manage.py migrate
uv run python manage.py runserver
```

You need a PostgreSQL server reachable at `DATABASE_URL`. This project never relies on SQLite. `python-ldap` is compiled during `uv sync`, so install the LDAP and SASL development headers first (`libldap2-dev` and `libsasl2-dev` on Debian and Ubuntu). PDF reports need Pango (`libpango-1.0-0`, `libpangoft2-1.0-0`).

## Default dev accounts

| Username | Password | Role |
| --- | --- | --- |
| `admin` | `admin` | Superuser (admin site) |
| `aavistin` | `aavistin` | Regular (non-staff) user |

Seeded by `python manage.py seed_dev_users` (`apps/accounts/management/commands/seed_dev_users.py`), which the `web` service runs on startup. They are for local development only. The command is idempotent and resets the passwords each time. With `DEBUG` off it refuses to use the default passwords: set `SEED_ADMIN_PASSWORD` and `SEED_AAVISTIN_PASSWORD` (both required) to seed a hosted test instance with passwords of your own. Nothing seeds these accounts outside `docker-compose.yml`'s dev commands.

## Default groups, organisation and roles

`python manage.py seed_dev_roles` (`apps/orgs/management/commands/seed_dev_roles.py`) runs right after `seed_dev_users` and seeds:

- One `django.contrib.auth.Group` per role in `apps.orgs.models.Role` (Viewer, Editor, Approver, Content curator, Organisation admin), as scaffolding for granting roles in bulk from Django admin.
- A **Default Organisation** and **Default Family**, so there is somewhere to create a product.
- The `aavistin` dev user in the Editor and Approver groups, both granted at Default Organisation scope. That is enough to add, edit, approve and (while unapproved) delete a product and everything under it from `/products/`, without Django admin. See `docs/adr/0008-product-level-authoring-and-approval-deferred.md`.

Same caveats as the users: local development only, idempotent, never run against a non-dev database.

## Tests and lint

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run manage.py check
uv run manage.py makemigrations --check --dry-run
```

These are the checks CI runs (`.github/workflows/ci.yml`). Tests need a running PostgreSQL (see `DATABASE_URL` in `.env` or `docker-compose.yml`); the default test run reuses its database (`--reuse-db`), so pass `--create-db` after changing migrations.

### End-to-end (browser) tests

The tests under `e2e/` drive the real UI in Chromium through Playwright. They are marked `e2e` and skipped by the default `pytest` run:

```bash
uv run playwright install chromium   # once
uv run pytest -m e2e
```

On failure, add `--screenshot only-on-failure --tracing retain-on-failure` to keep artefacts under `test-results/`. If a Chromium is already installed, point `PLAYWRIGHT_CHROMIUM_EXECUTABLE` at it instead of running the install.

## Working on requirement packages

Package content lives in `packages/` and is validated by the schemas in `schemas/`; see `packages/README.md`. Each directory there has its own `README.md` (ADR 0024). Import and approve packages with the admin pages or the management commands described in the README; `manage.py package_status` shows what is installed. A content change always bumps the version.

Never commit text from standards (EN, IEC, ISO): references, clause numbers and own summaries only.

## Working on the User Guide

The guide is Markdown in `docs/userguide/`, one `NN-slug.md` file per page, plus two generated pieces.

- **Preview in the app** at <http://localhost:8000/guide/>, or build the static site that GitHub Pages publishes:

  ```bash
  uv run manage.py export_userguide --output _site
  ```

- **Diagrams** are SVG files in `docs/userguide/images/`, referenced as `![description](images/name.svg)` and inlined into the page so they follow the theme (ADR 0043). Use the existing files as the pattern: boxes use the classes `d-box` and `d-key`, text `d-title` and `d-sub`, arrows `d-line` with a marker, and every file has a `<title>` and `<desc>`. Colours come from the design tokens in `static/css/base.css`; do not hard-code hex values in the SVG body. Check a new diagram in light and dark mode.
- **Licences page** is generated from `pyproject.toml`, the installed package metadata and `static/vendor/manifest.json`. Nothing to edit for Python packages. When you add a file to `static/vendor/`, add it to the manifest too (a test checks this).
- Internal links use the page slug: `[text](risk-assessment)`.

## Vendored front-end libraries

Alpine.js and htmx are copied into `static/vendor/` and served from the app's own origin, so pages and the end-to-end tests do not depend on a public CDN. No Node build is involved: the files are the `dist` builds published on npm, copied unmodified. Name, version and licence are in `static/vendor/manifest.json`.

To upgrade one, download the new `dist` file from npm, add it under a new versioned name, update `templates/base.html` and the manifest, and delete the old file.
