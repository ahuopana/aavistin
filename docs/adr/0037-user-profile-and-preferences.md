# 37. User profile and display preferences

Status: Accepted

## Context

Users could not choose a theme that followed them between browsers (the toggle only used `localStorage`), and all timestamps — approvals, audit history, stale detection — were shown in UTC. `docs/architecture.md` does not cover per-user preferences.

## Decision

- **`UserProfile`** (one-to-one with `User`, created on first use) holds `theme` (auto/light/dark), `locale`, `date_style` (locale or ISO 8601), `time_zone` and the avatar. A blank locale or time zone means the instance default (`LANGUAGE_CODE`, `TIME_ZONE`). It is a separate table so LDAP/OIDC sync never touches it.
- **Theme** is rendered server-side as `data-theme` on `<html>`, so there is no flash of the wrong theme. The header toggle saves to the profile for signed-in users and to `localStorage` for anonymous visitors (login page).
- **Locale only controls date and time formats.** The interface stays English; there are no translations to switch to, and activating a Django language would translate only framework strings. `apps.accounts.prefs` reads the locale's format directly, so adding a UI language later is a separate decision.
- **Time zone** is activated per request by `ProfileMiddleware`, so templates convert aware datetimes. Values are still stored in UTC. Templates show dates with `|userdate` / `|userdatetime` (`profile_tags`), which also apply the ISO style (`2026-10-13 14:05`, 24 h). `<input type="date">` values stay ISO regardless.
- **Identity fields** (name, email) are editable only for `auth_source=local`; for LDAP and OIDC users they are shown read-only because the directory is the source of truth.
- **Avatars** show initials on a per-user colour by default. An image can be uploaded only when uploads are enabled (`MEDIA_ROOT` set, ADR 0036); otherwise the upload field is hidden and initials are used. Uploads (PNG/JPEG/WebP/GIF, 2 MB, 4096² px) are decoded with Pillow and re-encoded to a 256×256 PNG, which drops EXIF and any embedded payload. Files are served by the login-protected `accounts:avatar` view, not from `MEDIA_URL`. Gravatar is deliberately not supported: it would send a hash of every user's email, and their IP, to a third party.
- **Password change** uses Django's `PasswordChangeView` at `accounts/profile/password/`, for `auth_source=local` only; directory users are told where their password is managed. The configured password validators apply and the session is kept.
- **Roles overview** is read-only: every `RoleAssignment` that reaches the user, directly or through a group, with scope (linked to the organisation, product family anchor or product) and how it was granted (`orgs.services.role_grants_for_user`). Inheritance is explained in a note rather than expanded into per-product rows. Roles are still managed by organisation admins.

## Consequences

- Pillow is a new dependency.
- Avatars are visible to every signed-in user, like names are.
- Deferred: notification preferences.
