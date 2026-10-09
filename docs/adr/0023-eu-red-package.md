# 23. EU RED package

Status: Accepted (content is not legally reviewed; see "Legal review")

## Context

RED is the second full legislation package after the CRA (ADR 0022) and follows the same approach: shared facts in `packages/common`, package-specific questions in the package, outcomes derived from concrete answers rather than self-declared classes, and fixtures for every rule. The maintainer asked for the Blue Guide (OJ C 247, 29.6.2022) to be the reference for EU product-law concepts and to be offered to users as guidance.

## Decisions

- **One package, `eu-red`,** covering the Directive and the acts that activate or add essential requirements: Delegated Regulations (EU) 2022/30 and 2019/320 and Directive (EU) 2022/2380. Their different dates live on the requirements (ADR 0019), not in separate packages. Only what is in force is modelled; any later repeal or amendment of 2022/30 in favour of the CRA is a future package version, not anticipated here. An info finding points cyber-relevant products to the CRA package.
- **Radio equipment means usable radio hardware.** In scope: product form not software, `wireless_interface_capability` not `not_present` or `present_physically_disabled`, and `wireless_enablement` not `disabled_manufacturer_update_only`. A radio that only a manufacturer update can enable is out of scope with a caution (the architecture's dormant-radio example); a user-enableable radio is in scope. This is an interpretation of Art. 2(1)(1) to review.
- **Enablement is a new shared question** at software level, so a release or an option can change it and the evaluation shows why scope changes (architecture, "Capability vs enablement").
- **Categories derived from facts.** 3(3)(d): communicates over the internet. 3(3)(e): processes personal data and is internet-connected, childcare, a toy or wearable. 3(3)(f): internet-connected and transfers money or value. Exemptions per 2022/30 Art. 2. 3(3)(g): smartphone. 3(4): an Annex Ia category that charges by cable. New shared facts went into `common` 1.2.0; `communicates_over_internet` also derives `has_data_connection`.
- **Module A gate** (Art. 17(3)): both harmonised-standard questions answered "yes, in full", the Art. 3(3) one only when an Art. 3(3) category applies. Unanswered means module A is not offered and a notified-body finding is raised, as the CRA package does for class I.
- **Findings only for in-scope products**, except the two disabled-radio findings, which explain why a product is out of scope. The demo seed's Aavistin fixtures expect no RED findings.
- **Blue Guide** is cited in `ref` fields and linked from shared questions on roles, commercial activity and placing on the market, and from the harmonised-standard question. RED-specific questions link to the Commission's RED page.

## Legal review

Before the package backs a real compliance decision, check against the Official Journal text:

- every `ref`, in particular Art. 10 paragraph numbers and Blue Guide section numbers (written without access to EUR-Lex from the build environment);
- the disabled-radio interpretation above;
- the 2022/30 Art. 2 exemptions: the shared vehicle question also covers L-category vehicles under Regulation (EU) No 168/2013, which may be broader than the exemption;
- the Annex Ia category list, charging thresholds and dates of Directive (EU) 2022/2380;
- the restrictions in the OJ citation of EN 18031-1/-2/-3.

## Consequences

- `common` 1.2.0 is a superset of 1.1.0, so the CRA package lints clean against either.
- Art. 4 and Art. 5 are not modelled until the Commission adopts the acts they depend on.
