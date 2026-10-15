# 44. Opt-in HTTPS hardening settings

Status: Accepted

## Context

`config/settings.py` honoured `X-Forwarded-Proto` but offered no way to turn on the other Django settings a deployment served over HTTPS should use. `manage.py check --deploy` reported five warnings on a production-style configuration, and the README had no production guidance beyond "use gunicorn behind a proxy" (`docs/architecture.md`, "Deployment").

Turning these on by default would break plain-HTTP local use and CI, which run with `DEBUG` off over HTTP.

## Decision

Environment variables, all off by default:

- `HTTPS_ONLY` turns on `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` together. One switch, because the three only make sense together.
- `SECURE_HSTS_SECONDS` (default 0) and `SECURE_HSTS_INCLUDE_SUBDOMAINS`. HSTS is separate because browsers remember it, so a wrong value is hard to undo.
- `CSRF_TRUSTED_ORIGINS`, a comma-separated list, for sites behind a proxy that rewrites the host.

The README's "Running in production" section tells operators to set them and to run `manage.py check --deploy`. The two remaining warnings with everything on (HSTS preload, and subdomains if not wanted) are choices, not defects.

## Consequences

- No behaviour changes unless a variable is set.
- A deployment must have its proxy send `X-Forwarded-Proto`, or `HTTPS_ONLY` causes a redirect loop. The README says so.
- Health checks over plain HTTP are redirected when `HTTPS_ONLY` is on; point them at HTTPS or send the forwarded header.
