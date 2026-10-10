# 30. Matrix logo and teal palette

Status: Accepted. Supersedes the logo, palette and display font decisions in ADR 0009; its token names and structure still apply.

## Context

The shield-and-A mark from ADR 0009 is thin at 16 px, says nothing specific about the product, and the royal blue and gold palette came from a separate design system rather than from Aavistin itself. Three alternatives were compared (a sharpened shield, a layered A, and a redesign from the product description alone). The redesign was chosen.

## Decision

- **Mark:** a 3×3 grid of rounded squares. It reads as a risk matrix and as an applicability table. Shade runs from low (bottom left) to high (top right); the top-right cell is the single accent colour and stands for the item that needs attention.
- **Wordmark:** lowercase `aavistin` in Outfit SemiBold (SIL Open Font License 1.1), outlined to path data so the SVGs render the same everywhere, as in ADR 0009.
- **Files** in `static/img/` keep their names: `aavistin-mark.svg`, `aavistin-mark-reversed.svg`, `aavistin-lockup-horizontal.svg`, `aavistin-lockup-horizontal-reversed.svg`. Three are new: `aavistin-mark-compact.svg` (tighter gaps, used as the favicon), `aavistin-mark-compact-reversed.svg` and `aavistin-mark-mono.svg` (one colour, for print). The reversed files are for the ink header bar, not for a mid-tone background.
- **Palette:** ink `#0f2a33` for brand chrome; a teal ramp `#d5eeea #a3dbd3 #5fbdb3 #2a8f8c`; orange `#f2711c` (`#ff9a4d` on dark) for attention.
- **Tokens:** names from ADR 0009 are kept, with values changed. `--color-brand` is ink; `--color-accent` is a darker teal for links and text (contrast 5.9:1 on white); the former gold fill tokens are renamed `--color-accent-fill` and `--color-on-accent-fill` (primary buttons, the active tab marker). A new `--color-attention` is used only for risk. Orange is not used for ordinary controls.
- **Typography:** Outfit replaces Space Grotesk for headings (`--font-display`). IBM Plex Sans and Mono are unchanged.

## Consequences

- The Google Fonts link in `templates/base.html` and the User Guide template now loads Outfit instead of Space Grotesk.
- The status colours (danger, warning, success) are unchanged, so an orange attention cell and a warning badge can appear together; they are meant to read as the same family.
- At 16 px the grid reads as a coloured block, not a distinct shape. The compact variant improves this but does not fix it; if the favicon needs to stand out in a crowded tab bar, revisit it.
- The unchosen proposals (shield, layered A) are not kept in the repository. They remain in the git history of the pull request that adopted this ADR.
