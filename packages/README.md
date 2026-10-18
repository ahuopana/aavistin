# Requirement packages

Regulation and requirement content lives here as versioned, schema-validated
packages (see `docs/architecture.md`, "Requirement sources"). This directory
is empty until Milestone 4 defines the package format and importer.

Do not commit text from standards (EN, IEC, ISO). Standards are referenced
by clause number with an own summary only. EU legal text (CELEX/ELI) may be
stored with attribution.

## Shared question sets

`common/` is a `question_set` package (import with `--kind question_set`).
It declares questions once; requirement packages reference them with
`"uses": ["common:uses_mfa"]` instead of redeclaring them. A question may
declare `implied_by` to derive its value from other answers. See
`docs/adr/0015-shared-question-library.md`.

## Versioning

A package's own `version` field identifies it; the importer refuses a
source/version pair that already exists ("bump the package version to
import changes"). Never edit an imported version in place, not even for
a citation fix or a README-only wording change inside the JSON: copy the
file to the next minor file name (`1.1.0.json` to `1.2.0.json`), bump
`version`, and list the previous version under `supersedes`.
