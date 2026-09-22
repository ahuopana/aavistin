# 2. RoleAssignment scope as explicit nullable FKs, not a generic relation

Status: Accepted

## Context

`docs/architecture.md` describes role assignments as records of
"(user or group, role, scope), inherited down the hierarchy organisation →
family → product," and prefers "a custom table over a generic per-object
permission library, for simpler hierarchical queries." It does not specify
the column shape for "scope," and Milestone 2 predates the `Product` model
(Milestone 3), so the full three-level hierarchy cannot be modelled yet.

## Decision

`RoleAssignment` has one nullable FK per scope level (`organisation`,
`product_family` for now) rather than a `ContentType` + object id generic
relation. Exactly one grantee (`user` xor `group`) and exactly one scope
column are required by database `CheckConstraint`s, not just application
validation. `Role` is a fixed `TextChoices` enum matching the table in the
architecture doc (viewer, editor, approver, content_curator, org_admin).

Resolution (`apps/orgs/services.py`) walks the fixed hierarchy explicitly:
a `product_family`-scoped lookup also matches assignments on that family's
`organisation`. When Milestone 3 adds `Product`, a `product` FK will be
added the same way, and resolution extended to also check the product's
family and organisation.

## Consequences

- Hierarchical queries stay simple `Q(organisation=...) | Q(product_family=...)`
  filters with real foreign-key joins and indexes, no `ContentType` lookup
  or per-model registration.
- Adding the `Product` scope level in Milestone 3 is a small, additive
  migration (one more nullable FK, one more constraint clause, one more
  `Q()` in `roles_for_user`), not a schema change to a generic table.
- The trade-off is a schema that grows by one column per hierarchy level
  instead of once; acceptable since the hierarchy is fixed at three levels
  per the architecture doc, not open-ended.
