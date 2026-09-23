# 1. Username uniqueness stays global, not scoped per auth source

Status: Accepted

## Context

`docs/architecture.md` says each user records an `auth_source` (`local`,
`ldap`, `oidc`) "to prevent collisions when the same username exists in two
sources." It does not say whether the same username string should be
allowed to exist once per source, or whether uniqueness stays global.

Django's auth framework requires `USERNAME_FIELD` (`username` here) to have
`unique=True` on the field itself (system check `auth.E003`); this is relied
on throughout `contrib.auth` (`get_by_natural_key`, `ModelBackend`, admin,
password reset). Scoping uniqueness to `(username, auth_source)` instead
means either bypassing that check or replacing large parts of the built-in
auth machinery.

## Decision

For Milestone 1, `username` stays globally unique, as Django expects.
`auth_source` is stored but does not relax uniqueness. If the same login
name exists in two sources (e.g. `alice` in both LDAP and a local
break-glass account), the LDAP backend introduced in Milestone 2 is
responsible for rejecting or namespacing the conflicting identity
explicitly (e.g. refusing to auto-provision over a `local` user, or
prefixing LDAP-sourced usernames) rather than relying on a composite
database constraint.

## Consequences

- Simpler, framework-compatible user model; no custom auth backend lookup
  logic needed yet.
- The actual collision-prevention behaviour (what happens when an LDAP sync
  meets an existing local username) is deferred to Milestone 2, when the
  LDAP backend is built, and must be designed then rather than assumed.
