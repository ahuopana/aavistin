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

### Attach evidence where you need it

You don't have to start from the evidence list. On a risk entry, each
control has an **attach evidence** link; on an assessment, each
requirement in force has one too. It opens the product's evidence list
in attach mode: pick an existing record with **Use this** (so one SBOM
backs several things without being uploaded twice), or add a new one,
which is linked for you. You return to where you started. A control
that is marked implemented or verified but has no evidence is flagged.

On an evidence record you can also link it to any requirement in force
for the product's configurations (a picker, not typed ids), edit its
title, description, link or note, validity and last audit (with an
"audited today by me" shortcut).

## New versions

When a document is replaced, add it as a **new version** from the old
record. The old one is marked superseded and keeps its links; the new
one starts unlinked. Open the new record and choose **Link to
everything the earlier version backs** to move over the links you have
reviewed, then unlink the old ones where they no longer apply.

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
