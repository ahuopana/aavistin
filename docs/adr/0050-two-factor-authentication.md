# 50. Two-factor authentication

## Status

Accepted

## Context

The security review flagged that the admin site and local accounts (including the break-glass accounts that stay enabled beside LDAP) were protected by a password alone. Approvers freeze compliance snapshots, so a stolen password is high impact.

## Decision

- **django-otp** with TOTP (RFC 6238) and single-use static recovery codes. Chosen over `django-two-factor-auth` because it does not replace the sign-in flow (`ThrottledLoginView`, ADR 0049) and over WebAuthn because TOTP works with every authenticator app (Microsoft Authenticator, Google Authenticator, Authy, 1Password and others) with no hardware. Passkeys (WebAuthn) are a planned later addition on the same foundation.
- **Who:** administrators (`is_staff` or `is_superuser`, whatever their `auth_source`) and every local account. LDAP and SSO users without admin rights are expected to be protected by their directory or identity provider. `MFA_ENFORCE=False` switches the policy off (local development, browser tests); it defaults to on.
- **When:** `MFAEnforcementMiddleware` redirects any signed-in user who needs a second factor and has not given it in this session. With no device, they go to enrolment at their next sign-in; with a device, to verification. Only enrolment, verification, sign-in and sign-out stay reachable. HTMX requests get an `HX-Redirect`. This covers `/admin/` and every other page.
- **Enrolment** (`/accounts/mfa/setup/`) shows a QR code and the key for manual entry, confirms with one valid code, and then shows ten recovery codes once. It is refused once a confirmed device exists, so knowing the password alone never lets anyone add a second factor to an enrolled account.
- **Recovery:** a recovery code works once. Users can generate a new set from their profile (the old set stops working). A user who lost both phone and codes asks an administrator to run `manage.py reset_mfa <username>`, which removes their devices so they enrol again at next sign-in. There is deliberately no self-service reset.
- **Guessing:** failed second-factor attempts are counted with the ADR 0049 throttle (same limit and window as sign-in), on top of django-otp's own per-device throttling.
- **Session:** the verified state lives in the session and ends at sign-out or session expiry (12 hours).

## Consequences

- Everyone local must enrol at their next sign-in; plan this with users. `docker-compose.yml` sets `MFA_ENFORCE=False` for local development, and CI's browser tests do the same.
- Until a person enrols, whoever signs in first with that account's password can enrol their own authenticator. For the first administrator and any shared break-glass account, enrol immediately after creating the account and keep the recovery codes offline.
- django-otp stores the TOTP secret in the database in readable form, so database access and backups are sensitive.
- Not covered: passkeys (later), MFA at the LDAP or SSO layer, and a self-service way to add or remove devices.
