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
`docs/adr/0007-background-job-backend.md`). `web` runs migrations and
seeds the default dev accounts below on every startup, before starting the
dev server.

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

## Running tests and lint

```bash
uv sync
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests require a running PostgreSQL instance (see `DATABASE_URL` in `.env`
or `docker-compose.yml`) — this project never relies on SQLite.
