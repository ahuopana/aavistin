# 11. UI component conventions: buttons, badges, add fields, tree rows

Status: Accepted

## Context

After adopting the design system (ADR 9), product and assessment screens
showed inconsistent controls: every button was a gold or grey outline,
status pills were hard to read, "add" inputs looked like loose fields
beside separate buttons, and child rows (revisions, options) were not
visually grouped under their parent. Not covered by `docs/architecture.md`.

## Decision

All values come from the existing CSS tokens in `static/css/base.css`.

- **Buttons:** secondary by default (neutral outline). `.button-primary`
  (solid gold) is used at most once per row or form, for Save and
  Approve. `.button-danger` is red text, with the border on hover.
  Header buttons are styled separately for the brand bar.
- **Badges:** `.badge` is a pill with a leading dot, coloured via
  `--badge-color`. Approved, closed and product-origin are success;
  draft is dashed and muted; inherited uses the focus colour;
  `badge-warning` marks needs-confirmation.
- **Add fields:** `.add-row` is one bordered field group with segmented
  inputs and an attached "+ Add" button. Enter submits.
- **Tree rows:** child rows in `.entity-table` use `.row-child` with
  `├`/`└` connectors, lighter dividers, and the add field as the last
  child (`.row-add` / `.cell-add`).
- **Hints:** guidance text lives behind an `.info` (i) icon, shown on
  hover or keyboard focus, via `data-tip`. Assessment justification
  fields appear only after the answer is changed (Alpine).

## Consequences

- New screens should use these classes rather than ad-hoc styles.
- Hint tooltips are CSS-only and not available to touch users without
  focus; acceptable for now, revisit if touch use grows.
- Slug is still a required field in add rows; deriving it from the name
  would need a backend change and is deferred.
