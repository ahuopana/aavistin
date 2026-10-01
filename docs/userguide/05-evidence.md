# Evidence

**Evidence** is the record that backs up a claim — that a requirement is
met, or that a control is in place. An evidence record is exactly one of
three kinds:

- A **file** (e.g. a test report, a certificate).
- An **external link** (e.g. a document in another system).
- A **plain text reference** (e.g. "see the QMS wiki").

Uploaded files are stored once per checksum — the same file used as
evidence for two different things is stored only once, and re-uploading
an identical file reuses the existing copy rather than duplicating it.

## Linking evidence

A single evidence record can be linked to more than one target: a
specific requirement (within a specific package version), a control, or
both. Each record also tracks who last audited it and when.

## Currency

Evidence can be marked **expired**, or become **superseded** when a
newer piece of evidence replaces it for the same target. An assessment
or risk approval that relies on evidence which has since expired or been
superseded (and never relinked) is flagged stale, the same way a changed
answer would be.

## Where you manage it

Evidence is managed from the product page it belongs to — a product's
evidence list shows every record linked to any of its requirements or
controls.
