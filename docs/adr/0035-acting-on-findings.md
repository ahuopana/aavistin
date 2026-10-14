# 35. Acting on findings and explaining the Compliance ratio

Status: Accepted

## Context

The assessment page listed findings as a level, a message and a source. Users could not tell what to do about them, which answers had raised them, or how they related to the Compliance ratio. The ratio itself ("Compliance 0/3") gave no route to the findings that held it down, and nothing explained what it measures.

## Decision

- A finding rule in a requirement package may carry **`guidance`**: plain text saying what the user should do about the finding (schema `schemas/package.schema.json`). It is optional, so existing packages stay valid; authors add it in new package versions.
- On the assessment page, each finding is joined back to its rule in the package version that raised it. The page shows:
  - the guidance;
  - **Based on**: the questions the rule's `when` expression reads, with their answers and links to the questionnaire (`apps/assessments/findings.py`).
  This also works for approved snapshots, since the package version is recorded with each finding.
- A short help box explains the three levels and what to do with each. Findings are listed most severe first.
- A finding whose package is out of scope for the configuration is marked "package not in scope". Packages may raise findings regardless of scope (e.g. a disabled radio that an update could enable), but such a finding does not count against compliance.
- **Compliance breakdown**: `apps.products.services.compliance_breakdown` lists, per configuration and in-scope package, the requirements counted and the blocking action-required findings. `compliance_ratio` is computed from it, so the two always agree. The breakdown page (`products:product_compliance`) is linked from every product Compliance ratio. Its findings link to the latest assessment's finding anchors.
- The Compliance bar has a hint describing the measure, and the Compliance Overview gains an **Action required** column.
- The ratio remains a package-level proxy. Tracking compliance per requirement (findings linked to requirements) is deferred: it changes the package format and the meaning of the ratio, and needs its own design.

## Consequences

- Package authors should write `guidance` for action-required findings first. The EU CRA and EU RED packages get it in their next versions.
- The breakdown evaluates each configuration live, as the ratio already did; there is no extra caching.
- When a product has no requirements to count, the Compliance bar says why instead of "no data yet": "Not in scope" (packages were evaluated and none applies), "None in force yet" (a package applies, but none of its requirements is in force yet). "No data yet" remains for products without configurations or active packages. The breakdown gives the reason per configuration.
