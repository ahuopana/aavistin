# 36. WhiteNoise for static files; uploads are opt-in

Status: Accepted

## Context

The app is going to be hosted on the internet for test and development. In production, gunicorn does not serve `/static/`, and the evidence upload directory (`MEDIA_ROOT`) was hard-coded to `BASE_DIR / "media"`, which in a container is ephemeral. Uploaded evidence was also served unauthenticated from `MEDIA_URL` when `DEBUG` was on.

## Decision

- **Static files:** serve them with WhiteNoise (`whitenoise.middleware.WhiteNoiseMiddleware`, right after `SecurityMiddleware`). `STATIC_ROOT` is `staticfiles/`; the Dockerfile runs `collectstatic`. With `DEBUG` off the storage is `CompressedManifestStaticFilesStorage` (hashed, compressed files); with `DEBUG` on it is the plain storage so local development needs no `collectstatic`. This avoids a separate nginx/Caddy static rule and a shared volume between containers.
- **Uploads are opt-in:** `MEDIA_ROOT` comes from the environment and defaults to empty. `settings.UPLOADS_ENABLED` is `bool(MEDIA_ROOT)`. When disabled, `store_evidence_file` raises `EvidenceError`, the evidence form hides the "Uploaded file" kind, and the download view returns 404. Link and reference-note evidence are unaffected. `docker-compose.yml` sets `MEDIA_ROOT=/app/media` for local development.
- **Downloads are authenticated:** uploaded files are no longer exposed under `MEDIA_URL`. They are streamed by `evidence:download` to logged-in users only. The `static()` media route in `config/urls.py` is removed.

## Consequences

- A deployment must mount a persistent volume at `MEDIA_ROOT` to enable uploads. Without one, uploads stay off rather than silently losing files.
- Any logged-in user can download any evidence file, matching the existing `evidence_detail` view, which also only requires login. Tightening this to per-product read roles is a separate change.
- Tests run with a temporary `MEDIA_ROOT` (autouse fixture in `conftest.py`).
