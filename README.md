# Aavistin

Open-source compliance and risk-assessment tool for product manufacturers.
Describe a product, answer one questionnaire, and see which regulations
apply (EU CRA, RED, LVD and others), what they require, and how the product's
risks are rated and treated. Approvals are frozen, audited records that go
stale when anything they relied on changes.

- **Using Aavistin:** the [User Guide](docs/userguide/01-getting-started.md),
  also in the app under `/guide/`.
- **Design:** [`docs/architecture.md`](docs/architecture.md), with decisions
  recorded in [`docs/adr/`](docs/adr/).
- **Working on Aavistin:** [`docs/development.md`](docs/development.md).
- **Licence:** [GNU AGPL v3](LICENSE).

## Try it

Requires Docker or Podman with Compose support.

```bash
docker compose up --build
```

Open <http://localhost:8000/> (or <http://localhost:8080/> once the first
start has written `.env`; see `WEB_PORT`) and sign in as `admin` / `admin`.
This starts a development stack with throwaway accounts. It is not for
real use; see [Running in production](#running-in-production). Ports,
accounts and the rest of the development setup are in
[`docs/development.md`](docs/development.md).

## Installing requirement packages

Regulation and other requirement content lives outside the application code
as versioned, schema-validated **packages** (see `docs/architecture.md`,
"Requirement sources"). Adding or changing a regulation means installing a
package, never changing Python code. The same mechanism carries risk-assessment
methods and catalogs.

Nothing is installed automatically, so a new system has no packages. Install
them from the Django admin; no command line is needed.

1. Get the package files. They are in [`packages/`](packages/) in this
   repository (one folder per package, one JSON file per version); download
   the ones you need to your computer.
2. Sign in to the admin (`/admin/`) as a user who may manage packages, open
   **Requirement packages** and choose **Import package**.
3. Choose the file, then the **kind** from the table below. Tick **Official**
   for the packages from this repository.
4. Read the result page. Aavistin has validated the file against its schema,
   linted it and run the package's own test examples. Check that there are no
   lint errors and that the examples passed, and look at the diff against the
   previous version, if there is one. Importing never switches a package on.
5. Back in the list, tick the package and choose **Approve selected packages**
   from the action menu. Only approved packages affect assessments. Approving
   a new version replaces the previous one; assessments that used the old one
   are marked stale so they get reviewed.

Import in this order, because a package can only be imported once what it
refers to is approved. Take the highest version of each package; older
versions are kept for history.

| Order | Package | Kind | What it is |
| --- | --- | --- | --- |
| 1 | `common` | Shared question set | Questions several regulations ask, answered once |
| 2 | `default-cia-5x5` | Risk method | The default risk scoring (severity × likelihood) |
| 3 | `eu-cra`, `eu-lvd`, `eu-red` | Requirement (applicability) | The EU Cyber Resilience Act, Low Voltage Directive and Radio Equipment Directive |

To explore with invented data instead, import `demo-widget-safety`
(requirement), `demo-safety-5x5` (risk method) and `demo-widget-risks` (risk
catalog). They are not real regulations. Each package folder has a `README.md`
saying what it covers, its dependencies and its versions.

The EU packages are not legal advice and have not yet been legally reviewed;
their own READMEs list what to verify before relying on them.

<details>
<summary>Command line instead</summary>

Run these inside the `web` container, which has the app's dependencies and the
database connection (`exec` if the stack is up, `run --rm` otherwise):

```bash
docker compose exec web python manage.py import_package packages/common/1.4.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.4.0
docker compose exec web python manage.py package_status
```

`import_package` does the same checks as the admin page and does not approve.
</details>

## Running in production

The `docker-compose.yml` in this repository is for development: it runs with
`DEBUG` on, mounts the source into the container, publishes the database port
and seeds accounts with known passwords. For anything other than your own
laptop:

**Run it properly**

- Build the image from the `Dockerfile` (it runs gunicorn, serves static files
  with WhiteNoise and runs `collectstatic`) and put it behind a reverse proxy
  that terminates TLS. Run three processes from that image: the web server
  (the default command), `python manage.py db_worker` and
  `python manage.py scheduler`. Run `python manage.py migrate` on each release.
- Use a PostgreSQL server of your own with a strong password, not reachable
  from the internet, and back it up. If you enable evidence file uploads,
  mount persistent storage at `MEDIA_ROOT` and back that up too.
- Create your first administrator with `python manage.py createsuperuser`.
  Never run `seed_dev_users` or `seed_dev_roles`: they create accounts with
  known passwords.

**Configure it securely** (environment variables; see `.env.example`)

| Setting | Production value |
| --- | --- |
| `DEBUG` | `False` (the default). With it on, errors expose settings and code. |
| `DJANGO_SECRET_KEY` | A long random value that only this deployment knows, for example `python -c "import secrets; print(secrets.token_urlsafe(64))"`. Keep it out of the repository and out of images. |
| `DJANGO_ALLOWED_HOSTS` | Your real host names only, for example `aavistin.example.org`. |
| `CSRF_TRUSTED_ORIGINS` | Your site's origin, for example `https://aavistin.example.org`. |
| `HTTPS_ONLY` | `True`: redirects HTTP to HTTPS and marks the session and CSRF cookies secure. Your proxy must send `X-Forwarded-Proto`, or you get a redirect loop. |
| `SECURE_HSTS_SECONDS` | Once HTTPS works, `31536000`. Start with `3600`: browsers remember this setting. |
| `DATABASE_URL` | Your production database, with its own credentials. |
| `AUTH_LDAP_*` | Use `ldaps://`, not `ldap://`, if you enable LDAP. |
| `MFA_ENFORCE` | `True` (the default). Administrators and local accounts must set up an authenticator app at their next sign-in; enrol your first administrator immediately. See [ADR 0050](docs/adr/0050-two-factor-authentication.md). |
| `CLIENT_IP_HEADER` | Behind a proxy, the header it sets with the client address (for example `HTTP_X_FORWARDED_FOR`), so sign-in throttling tells clients apart. Only if the proxy overwrites it. |
| `REPORT_VERIFY_ENABLED` | `False` turns the public `/verify/` page off. Upload size, rate and sign-in throttling limits are listed in `.env.example` ([ADR 0049](docs/adr/0049-throttling-and-upload-limits.md)). |

Then run the Django deployment check and resolve what it reports:

```bash
python manage.py check --deploy
```

With the settings above, only two optional HSTS items remain (subdomains and
preload); the rest of the report should be empty.

**Operate it carefully**

- Set each organisation's separation-of-duties policy to `warn` or `enforce`
  (in the admin), so the person who edited the answers is not the one who
  approves them.
- Give people the lowest role they need (Viewer, Editor, Approver) and prefer
  granting roles on a product family or product over the whole organisation.
- Keep dependencies current: rebuild the image regularly and watch for
  security releases of Django and the other packages listed on the
  User Guide's Licences page.
