# Reports

A **report** is a PDF of one configuration: its product, hardware,
software and options, and, if you choose, its assessment, risks,
mitigations and evidence. Use it to hand a configuration's state to
someone outside Aavistin, such as an auditor or a customer.

## Creating a report

Open a product's **Compliance** page and choose **Report** next to the
configuration. Then:

1. Tick the sections to include.
2. Edit the title if you like. It defaults to "Product – Configuration"
   and appears in the header of every page.
3. Choose **Download draft** or **Issue approved report**.

The **Reports** link on the Compliance overview lists every approved
report you can see.

## Drafts and approved reports

| | Draft | Approved report |
| --- | --- | --- |
| Who | Anyone with a role on the product | An Approver on the product |
| Data | Live: whatever the assessment and risk register say now | Frozen: the approved assessment and risk snapshots |
| Stored | No. It is downloaded and not kept | Yes, with a report ID, the content and the PDF |
| Verifiable | No | Yes |
| Marked | "DRAFT, not verifiable" | Report ID and "Approved" in every footer |

An approved report can be issued only when every assessment, risk or
mitigation section you ticked has an approved snapshot that is not
stale. If one is missing or stale, the form says which. Product,
hardware, software, options and evidence are not frozen: the report
copies them as they are when it is issued.

An approved report cannot be changed or deleted. If something changes
later, issue a new one.

## What is on the pages

- **Header:** the Aavistin logo and the report title.
- **Footer:** "Page X of Y", the report ID and the status.
- **Cover:** the configuration, who generated the report and when, the
  assessment and risk snapshot IDs with their approvers (and a
  separation-of-duties warning if the approver also edited an answer),
  and a hash of the report content.

Reports contain requirement labels and references from the packages,
never text from standards. Evidence is listed with its title, kind,
file hash, validity and links; the files themselves are not included.

## Verifying a report

Every approved report carries its ID, like `AAV-7K3Q-9XMD-2PWH`. Anyone
can open `/verify/<report ID>/` without signing in. The page shows the
title, who generated it, when, and the SHA-256 of the PDF. Upload a PDF
there to check that it is identical to the one issued. The page also
warns if an assessment or risk snapshot the report relied on has gone
stale since. Drafts are never recorded, so a draft cannot be verified.
