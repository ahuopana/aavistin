# Organisations and products

Everything in Aavistin hangs off this hierarchy:

```
Organisation
  Product family
    Product
      Hardware variant
        Hardware revision (with target markets)
      Software release
        Software option
      Configuration (a revision + a release + optional options)
```

## Organisations and product families

An **Organisation** is the top-level entity roles are granted against —
typically the manufacturer itself, or one of its business units. A
**Product family** groups related products (e.g. "Sensors", "Gateways")
and belongs to exactly one organisation.

## Products

A **Product** belongs to a product family. Under it:

- **Hardware variants** are physical variants of the product (e.g.
  different enclosures or radio options). Each variant has one or more
  **hardware revisions**, and each revision can be set against one or
  more **target markets** (e.g. EU, US) — this is what determines which
  requirement packages apply.
- **Software releases** are versions of the product's firmware or
  software. Each release can have **software options** (e.g. optional
  feature packs) that change what applies.
- **Configurations** tie a specific hardware revision to a specific
  software release, with optional software options — this is the unit
  an assessment is actually performed against.

## Approval

Hardware variants, hardware revisions, software releases, software
options and configurations can each be **approved** once they're ready.
An approved entity is locked against further edits and deletion — this
is what "frozen" means when an assessment later says its snapshot is
based on approved data.

## Where this feeds in

A configuration's hardware revision determines its target markets, which
determine which requirement packages are active for it — the subject of
the next section, [requirement packages and assessments](requirement-packages-and-assessments).
