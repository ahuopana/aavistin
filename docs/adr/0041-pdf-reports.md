# 41. PDF reports: drafts on the fly, approved reports stored and verifiable

Status: Accepted

## Context

`docs/architecture.md` mentions reports (Viewers "read ... reports"; the separation-of-duties warning is "shown in the report") but does not specify them. This ADR was decided with the product owner in conversation.

## Decision

- **One report per configuration.** The product, hardware, software and options are part of the configuration's header block, not separate reports.
- **Selectable sections:** product, hardware, software, options, assessment, risks, mitigations (treatments and controls), evidence. The report is built from the selected sections only.
- **Two kinds of output:**
  - *Draft.* Generated on the fly and streamed as a download. Nothing is stored, not even an ID. It is marked "DRAFT, not verifiable" with generation time and generator. Any role on the product may download one.
  - *Approved report.* Issued only when every selected snapshot section (assessment, risks, mitigations) comes from an approved, non-stale snapshot, and at least one is selected. It needs the Approver role. It is stored as a `Report` row: random report ID, configuration, title, sections, the content as JSON, the SHA-256 of the content, the PDF bytes and their SHA-256, the generator and the source snapshot ids.
- **Content is captured at generation time.** Snapshots are frozen but product, hardware, software and evidence data are live, so the stored content copies them. The PDF is rendered from the stored content only.
- **PDF bytes live in the database** (`BinaryField`), not on disk: file uploads are opt-in (`MEDIA_ROOT`, ADR 0036) and reports must work without them.
- **Verification** is public (`/verify/<report-id>/`, no login) and exists for approved reports only. A draft or unknown id gives the same "not found" page. The page shows the ID, title, generator, time, the PDF's SHA-256, and warns if a source snapshot has since gone stale. A visitor can upload a PDF to check its hash against the stored one.
- **Immutable.** Approved reports cannot be edited or deleted in the app. Their configuration is `PROTECT`ed.
- **Layout.** Header: Aavistin logo and name on one side, the report title (default "Product – Configuration", editable when generating) on the other. Footer: "Page X of Y", report ID and status. The cover lists both snapshot ids and the content hash.
- **Rendering:** WeasyPrint, from HTML templates, so the layout reuses the web stack. It needs pango (Dockerfile and CI).
- **Cover and wording.** The cover names the document type from the sections chosen ("Product Compliance and Risk Assessment Report", and shorter variants), the generator as "Name, Role" (highest role on the product; the user model has no job title), a readable timestamp, and the Aavistin version: `AAVISTIN_VERSION` if set (the Dockerfile bakes it from a build argument), else `git describe --tags --always --dirty`. Package ids are shown as the package's own labels, and findings sorted by level.
- **Out-of-scope regulations** are listed only if the user ticks the option at generation time. Findings are always listed: the engine evaluates a package's finding rules regardless of its scope (ADR 0035), and such findings are marked "package not in scope", as in the web UI.
- **Signature** means the named generator plus the approvers recorded in the snapshots. No cryptographic PDF signature (PAdES).
- **Location:** generate from the product's Compliance page; "Reports" list under the Compliance menu.

## Consequences

- No purge job or expiry is needed since drafts are never stored.
- There is no record of who downloaded a draft.
- No demo-data label exists yet (the architecture's demo seed rule); reports of demo products are not marked as such.
- Standards text is never included: only labels, references and own summaries from packages.
