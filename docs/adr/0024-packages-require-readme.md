# 24. Every package directory has a README

Status: Accepted.

## Context

Packages have an import order (`common` before `eu-cra`) and quirks such as the file name differing from the package `version` field. When `common` had no README, nothing told a new user how to import it or that other packages depend on it.

## Decision

- Every directory under `packages/` contains a `README.md`. It says what the package is, its kind, what it depends on, and the exact import and approve commands. Packages that are not real regulation content (demos, test fixtures) say so.
- A test (`PackageReadmeTests` in `apps/packages/tests.py`) fails if a package directory lacks one.
- The importer already refuses a package whose `uses` names an unapproved question set, so the README states the order and the importer enforces it.
