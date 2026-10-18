# eu-red

The EU Radio Equipment Directive, Directive 2014/53/EU (CELEX `32014L0053`), as a requirement package, together with the acts that activate or add its essential requirements:

- Delegated Regulation (EU) 2022/30 (Art. 3(3)(d), (e), (f): network protection, privacy, fraud), applicable from 1 August 2025 under Delegated Regulation (EU) 2023/2444;
- Delegated Regulation (EU) 2019/320 (Art. 3(3)(g): emergency caller location on smartphones);
- Directive (EU) 2022/2380 (Art. 3(4), 3a: common charger).

General product-law concepts (making available, placing on the market, economic operators, harmonised standards, conformity assessment modules, CE marking) follow the Commission's Blue Guide on the implementation of EU product rules 2022, OJ C 247, 29.6.2022 ([EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=oj%3AJOC_2022_247_R_0001)). The design decisions are in `docs/adr/0023-eu-red-package.md`.

**Not legal advice, and not yet legally reviewed.** The article and Blue Guide references in `ref` fields, the scope interpretation of disabled radios, and the exemptions were written from the acts' structure and must be checked against the Official Journal text before the package backs a real compliance decision. The review list is in the ADR.

## What it covers

- **Scope:** hardware with a radio that can intentionally emit or receive (including receive-only and radio modules); software alone is not radio equipment. Excluded: no commercial activity, Annex I equipment (amateur radio not made available, marine equipment, airborne products, custom evaluation kits for R&D), and equipment used exclusively for defence or public and State security.
- **Disabled radios:** physically disabled radios and radios that only a manufacturer update can enable are out of scope, with an info or caution finding. A radio the user can switch on is in scope.
- **Roles:** manufacturer, importer, distributor, authorised representative. An importer or distributor that places the product under its own name or modifies it is treated as the manufacturer (Art. 14).
- **Classifications:** Art. 3(3)(d), (e), (f) per Delegated Regulation 2022/30, with its exemptions (civil aviation, type-approved vehicles, electronic road tolls; medical and in-vitro diagnostic devices for (e) and (f)); Art. 3(3)(g) for smartphones; Art. 3(4) common charger categories. Several can apply at once.
- **Requirements:** essential requirements Art. 3(1)(a) (from 1.1.0: health protection plus the eight LVD Annex I safety objectives, with no voltage limit), 3(1)(b), 3(2), 3(3)(d)-(g), 3(4), 3a; manufacturer obligations (Art. 10, 17, 18, 19, 20, 21); authorised representative (Art. 11), importer (Art. 12) and distributor (Art. 13) obligations.
- **Dates:** each dated requirement applies only to units placed on or after its date (2022/30: 1 August 2025; 2019/320: 17 March 2022; common charger: 28 December 2024, laptops 28 April 2026). While no placement date is answered, nothing is hidden.
- **Routes:** module A only when harmonised standards for Art. 3(2) and every applicable Art. 3(3) requirement are applied in full (for 2022/30: EN 18031-1/-2/-3 without the options the OJ citation restricts); modules B+C and H always (Art. 17).
- **Findings:** notified body required, dormant or user-enableable radio, missing safety risk assessment, technical documentation, electrical ratings, declaration of conformity, CE marking, identification or instructions in local languages, an unchecked supplier (1.1.0), shared default passwords, unverified updates, no update mechanism, unprotected personal data in transit, role notes, and a pointer to the CRA for cyber-relevant products.
- **Question groups:** the questionnaire follows the Directive's structure: product and role, radio, exclusions, placement, network/privacy/fraud categories and measures, charger and emergency location, conformity (ADR 0025).
- **Fixtures:** 46 example products in 1.0.0, 49 in 1.1.0, including the demo seed's expected result for Aavistin (out of scope: no radio equipment).

**Depends on** the shared question library `packages/common`, which must be approved first; the importer refuses this package otherwise. 1.0.0 needs `common` 1.2.0 or later, which adds `wireless_enablement`, `communicates_over_internet`, `transfers_money_or_value`, `is_toy`, `is_childcare_product` and `is_wearable` to 1.1.1. 1.1.0 needs `common` 1.4.0, for the safety and CE-marking process questions it shares with `eu-lvd`.

## Versions

- `1.0.0` (`2014-53@2026-10`): first version. Art. 3(1)(a) is one requirement that points to the LVD safety objectives.
- `1.1.0` (`2014-53@2026-10.1`, supersedes 1.0.0): Art. 3(1)(a) is broken down into health protection and the eight LVD Annex I safety objectives (own summaries; the objectives apply without the LVD voltage limits), and the questionnaire asks the safety and CE-marking process questions that `eu-lvd` asks, with action-required findings for a "no". A radio product is excluded from `eu-lvd`, so without this it lost those checks (ADR 0042). Not legally reviewed either.
- `1.2.0` (`2014-53@2026-10.2`, supersedes 1.1.0): citation fixes only, no change in behaviour. The Annex I exclusions cite Art. 1(2) and defence or security Art. 1(3) (Art. 1(4) is the LVD disapplication); retention is Art. 10(4), series production Art. 10(5), corrective action Art. 10(11)-(12); the notified-body trigger is Art. 17(4).

## Known limitations

- Art. 4 (radio equipment and software combinations) and Art. 5 (registration) depend on Commission acts that have not been adopted; not modelled.
- Harmonised standards are referenced, never quoted; the questions about them stay generic.
- The vehicle exemption reuses the shared question about vehicles type-approved under Regulation (EU) 2019/2144 or (EU) No 168/2013, which is broader than the 2022/30 exemption (see the ADR).

## Importing

Import and approve the shared question library first, then this package. Run inside the `web` container:

```bash
docker compose exec web python manage.py import_package packages/common/1.4.0.json --kind question_set --official
docker compose exec web python manage.py approve_package common 1.4.0
docker compose exec web python manage.py import_package packages/eu-red/1.2.0.json --kind requirement --official
docker compose exec web python manage.py approve_package eu-red "2014-53@2026-10.1"
```

Approving 1.2.0 supersedes an approved 1.1.0 (and so on down the chain). The file names are `1.0.0.json`, `1.1.0.json` and `1.2.0.json`; the package's own `version` field, which `approve_package` keys on, is `2014-53@2026-10` and `2014-53@2026-10.1`. Content changes always bump that version.
