# 43. Production security settings and product read access

## Status

Accepted

## Context

A security review found two gaps:

1. Product-scoped pages were readable by any logged-in user who guessed an id. Writes checked `has_role(...)`, but the product detail, risk register, assessment and evidence views (including evidence file download) only used `@login_required`. Reports and the product compliance page already checked for a role.
2. `config/settings.py` carried no production hardening: a published fallback `SECRET_KEY`, no secure cookies or HSTS, and `X-Forwarded-Proto` trusted unconditionally while gunicorn listens on `0.0.0.0`.

## Decision

**Read access.** `apps.orgs.services.can_view_product` / `require_product_view` define who may read a product: a superuser, or anyone holding any role that reaches the product (directly, via its family, via its organisation, or through a group). Views call `require_product_view` and the helper raises `Http404`, not a redirect or 403, so product ids can't be probed. Write views keep their stricter `has_role(...)` checks. `apps/orgs/test_read_access.py` covers every product-scoped read URL.

**Settings.**

- Outside `DEBUG`, startup fails with `ImproperlyConfigured` if `DJANGO_SECRET_KEY` is empty or a placeholder.
- Outside `DEBUG`, session and CSRF cookies are `Secure` by default, with HttpOnly and SameSite=Lax, a 12 hour session lifetime (`SESSION_COOKIE_AGE`), and HSTS of one hour (`SECURE_HSTS_SECONDS`, raise once HTTPS is confirmed).
- `SECURE_PROXY_SSL_HEADER` is now **opt-in** via `TRUST_X_FORWARDED_PROTO=True`. Enable it only when a reverse proxy always overwrites `X-Forwarded-Proto` and the app port isn't reachable directly.
- `SECURE_SSL_REDIRECT` defaults to off (the proxy normally redirects); `DJANGO_CSRF_TRUSTED_ORIGINS` is configurable.
- Minimum password length is 12.
- CI runs `manage.py check --deploy --fail-level WARNING` against production-like settings.

## Consequences

- **Deployments behind a TLS proxy must set `TRUST_X_FORWARDED_PROTO=True`** (and `DJANGO_CSRF_TRUSTED_ORIGINS` if the public origin differs). Without it, Django sees plain HTTP, and Secure cookies plus the CSRF origin check will reject logins. This is deliberate: it fails closed.
- A deployment with no TLS at all (evaluation over plain HTTP) must set `SESSION_COOKIE_SECURE=False` and `CSRF_COOKIE_SECURE=False` explicitly.
- Existing users may be asked to sign in again after 12 hours instead of two weeks.
- Existing passwords shorter than 12 characters keep working; the rule applies when they are changed or set through forms.
- Not covered here: a Content-Security-Policy, login throttling, admin MFA, upload limits, and container hardening. Each needs its own decision.
