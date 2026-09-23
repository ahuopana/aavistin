# 9. Design system adoption: palette, typography and logo

Status: Accepted

## Context

`docs/architecture.md` does not specify a visual identity — colors,
type, or a logo — for the application shell. `templates/base.html` and
`static/css/base.css` (milestone 1, "base layout") shipped with a
placeholder neutral palette and system fonts, and `.app-brand` was plain
text.

A brand was developed separately in a Claude Design System artifact:
dark royal blue, gold and white as primary colors, with a shield-and-"A"
mark whose vertical stroke is a gold checkmark woven through the legs.
That work is finished and approved; this ADR records adopting it into
the actual templates and stylesheet, since it's a decision not covered
by `docs/architecture.md`.

## Decision

- `static/css/base.css`'s CSS custom properties keep their existing
  names (`--color-bg`, `--color-surface`, `--color-border`,
  `--color-text`, `--color-text-muted`, `--color-danger`,
  `--color-warning`, `--color-success`) but take the new palette's
  values for light and dark themes. `--color-accent` now points at the
  gold token (links, focus highlights, active states, badges — not
  brand chrome). Two variables are added: `--color-brand` (royal blue)
  and `--color-brand-contrast` (white), used for the header bar and
  logo-adjacent chrome.
- Typography: Space Grotesk (display/headings), IBM Plex Sans (body),
  IBM Plex Mono (code), loaded via Google Fonts `<link>` tags in
  `templates/base.html` and exposed as `--font-display`/`--font-sans`/
  `--font-mono`.
- The spacing scale gains `--space-5` (32px) and `--space-6` (48px)
  alongside the existing `--space-1`..`--space-4`.
- `.app-header` becomes a solid `--color-brand` bar; `.app-brand` is now
  the horizontal lockup logo (`static/img/aavistin-lockup-horizontal-reversed.svg`)
  instead of plain text, sized to the header height.
- Logo assets live under `static/img/`: `aavistin-mark.svg` and
  `aavistin-mark-reversed.svg` (mark alone, light/dark contexts),
  `aavistin-lockup-horizontal.svg` and
  `aavistin-lockup-horizontal-reversed.svg` (mark + wordmark). The
  favicon uses `aavistin-mark.svg` directly.

## Consequences

- Any new UI should pull colors, spacing and type from these tokens
  rather than hard-coding values, matching the design system's own
  usage rules (e.g. gold for interactive/accent, blue reserved for
  brand chrome, not body links).
- Google Fonts is now an external dependency for page render; no build
  step is introduced (plain `<link>` tags, consistent with "no Node
  build unless an ADR justifies it" — this ADR does not add one).
- The logo SVGs are hand-authored path/polyline geometry (no source
  design file exists in the repo); any future rework of the mark should
  treat these SVGs as the source of truth.
