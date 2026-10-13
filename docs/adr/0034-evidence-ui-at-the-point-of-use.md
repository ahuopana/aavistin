# 34. Evidence UI at the point of use

Status: Accepted

## Context

The evidence list, upload, link and delete pages existed (ADR 0011), but evidence could only be linked from the evidence detail page, with requirements typed as raw package ids, and records could not be edited or replaced by a new version in the app.

## Decisions

- **Attach mode.** The product evidence list accepts `?control=<pk>` or `?requirement=source|version|id` and `next=<url>`. It then offers "Use this" on every existing record (`evidence:attach`) and links any newly created record to the target. `next` is honoured only for same-site URLs. Risk-entry controls and the requirements-in-force list of an assessment link into it.
- **Requirement picker.** Requirements are offered from the current evaluation of the product's configurations (labels and references from package content), never from a hard-coded list. Typed source/version/id are still accepted by the endpoint.
- **Edit.** Title, description, link, note, validity and last audit are editable; the kind and a stored file are not (a different document is a new version, which keeps what was audited reproducible). "Audited today" records the editing user.
- **New versions.** Creating evidence with `supersedes` marks the old one superseded and does not move links; a button on the new record copies the old one's links (`copy_links`), leaving the old links in place until someone removes them. This is the "someone reviews and relinks" step of the architecture.
- **Hints, not rules.** A control that is implemented or verified without evidence is flagged on the risk entry. Nothing is enforced, since evidence may live outside the product (a certificate held by a supplier would be a note).

## Consequences

- Issue trackers (GitHub, Jira, Redmine) are not modelled: a tracker issue is a work item, not proof. Linking issues to planned controls and showing their status is a separate component (`docs/plans/issue-status-component.md`).
- Requirement choices run an evaluation per configuration when the evidence page is opened; acceptable at current product sizes.
