# 34. Impact categories come from method packages

Status: Accepted

## Context

A threat's consequences were classified into five impact categories fixed in code (`ImpactCategory`): safety, property damage, operational, financial and privacy. Compliance harm, such as data stored outside the regions a contract or regulation allows, fitted none of them well: privacy covers only personal data, and financial hides fines, termination and loss of market access among other costs. Common risk methods treat legal, regulatory and contractual impact as its own category. Hard-coding the list in the application also went against keeping risk content in packages.

## Decision

- A **method package** may declare `impact_categories`: `[{id, label, description?, links_to_hazard?}]` (schema `schemas/method.schema.json`; the linter rejects duplicate ids).
- A threat's consequence may use the categories of the **approved methods that rate the threat**. The form offers them, and the view rejects any other.
- `links_to_hazard` replaces the hard-coded safety/property-damage pair: only such a consequence may link a hazard entry, and the cross-method consistency rules apply to it.
- A method that declares no categories gets `apps.risk.impact.DEFAULT_CATEGORIES`, the previous five. Existing method packages and data keep working unchanged.
- `ThreatConsequence.impact_category` stores the id, without fixed choices. Its label comes from the approved methods, with a readable fallback for an id that no method declares any more.
- `default-cia-5x5` 1.1.0 declares the five plus **Legal and contractual**.

## Consequences

- Changing a method's categories is a new package version, reviewed and approved like any package. Consequences keep their ids; an id dropped in a newer version still displays, but can't be chosen for new consequences.
- Reputation, or other categories, can be added the same way when a method needs them.
- Compliance rules themselves (e.g. allowed data regions) still belong in requirement packages as questions and findings; the category covers the consequence when a threat breaches them.
