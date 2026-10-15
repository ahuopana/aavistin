# 44. Login throttling, upload limits and optional public verification

## Status

Accepted

## Context

The security review (ADR 0043 follow-up) found three abuse paths: unlimited password guessing against local accounts (including the break-glass `ModelBackend` that stays on beside LDAP), evidence uploads with no size, type or content checks, and the unauthenticated `/verify/<id>/` page, which read the whole uploaded file into memory and could be hit without limit.

## Decision

**Shared throttle store.** `apps.core.ThrottleEvent` (scope, key, timestamp) with `apps.core.throttle` implements a sliding-window limit in PostgreSQL. It keeps limits correct across gunicorn workers and restarts without adding Redis (the project avoids extra services, ADR 0007). Old rows are pruned on write.

**Login throttling.** `apps.accounts.throttle.ThrottleBackend` is the first authentication backend. While a username or client address is locked it raises `PermissionDenied`, so `authenticate()` stops before any backend checks the password. This covers the sign-in page, the admin login and LDAP alike, and a correct password during a lock does not log in. Failures are recorded from `user_login_failed`, for existing and unknown usernames alike, so a lock reveals nothing about which accounts exist. A successful login clears that username's failures. Defaults: 5 failures per username and 30 per address within 15 minutes (`LOGIN_THROTTLE_*`, `LOGIN_THROTTLE_ENABLED`). Refused attempts are not recorded, so an attacker cannot extend a lock indefinitely. The sign-in page says when sign-in is locked.

Trade-off: a determined attacker can lock a known username out for 15 minutes. We accept this over unlimited guessing; the address limit and the short window bound the harm, and administrators can clear `ThrottleEvent` rows. Behind a proxy set `CLIENT_IP_HEADER` (for example `HTTP_X_FORWARDED_FOR`), only if the proxy overwrites that header; the last entry is used. Otherwise every client appears to share the proxy's address.

**Evidence uploads.** `store_evidence_file` rejects empty files, files over `EVIDENCE_MAX_UPLOAD_BYTES` (25 MB), extensions outside `EVIDENCE_ALLOWED_EXTENSIONS`, and files whose first bytes contradict their extension (PDF, PNG, JPEG, GIF, ZIP and Office containers). The client-sent content type is ignored; the stored type derives from the file name. Downloads were already `attachment`; they now also carry `Content-Security-Policy: sandbox` and `nosniff`. HTML and SVG are not in the default allowlist because they can carry script. There is no malware scan; deployments that need one should scan at the proxy or storage layer.

**Request size.** `RequestSizeLimitMiddleware` answers 413 for any request whose `Content-Length` exceeds `MAX_REQUEST_BYTES` (largest upload limit plus 1 MB) before Django reads the body. `DATA_UPLOAD_MAX_MEMORY_SIZE` is set to 2 MB for non-file form data. The reverse proxy should enforce the same cap (nginx `client_max_body_size`), because chunked bodies without a length are not seen by the middleware.

**Public verification.** `REPORT_VERIFY_ENABLED` (default on) switches `/verify/<id>/` off entirely: it returns 404, and the report page and the PDF footer stop mentioning it. The PDF footer is decided when a report is issued, so already-issued PDFs keep their text. When on, requests are limited per client address (`REPORT_VERIFY_RATE_LIMIT` per `REPORT_VERIFY_RATE_WINDOW_SECONDS`, default 20 per 10 minutes, answering 429 with `Retry-After`), uploads are capped at `REPORT_VERIFY_MAX_BYTES` (20 MB), and the file is hashed in chunks instead of being read into memory. Unknown ids count toward the limit, which slows id enumeration.

## Consequences

- One new table and migration (`core.0001`).
- Uploads of unlisted types (for example `.html`, `.svg`, `.exe`) now fail; add extensions through `EVIDENCE_ALLOWED_EXTENSIONS` if a deployment needs them.
- Shared offices or NATed networks share the per-address limits; raise `LOGIN_THROTTLE_MAX_FAILURES_PER_IP` if that bites.
- Not covered: MFA for the admin, a Content-Security-Policy for pages, and malware scanning.
