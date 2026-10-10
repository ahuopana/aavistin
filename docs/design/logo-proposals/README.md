# Logo proposals

Three alternatives to the current Aavistin logo, each built around a different aim. Nothing here is used by the application yet: `static/img/` and the CSS are unchanged until a direction is chosen. Open `compare.html` (or `preview.png`) to see them side by side with the current logo.

Each directory holds the same set of files: `mark`, `mark-reversed`, `mark-compact` and `mark-compact-reversed` (for favicons and sizes up to about 32 px), `mark-mono` (one colour, for print and stamps) and `lockup-horizontal` with its reversed twin. All SVGs are hand-built paths; the wordmarks are outlined, so no font is needed at runtime.

## A · Shield: legibility and craft (`a-shield/`)

Keeps today's idea (a shield around an A with a gold bar) and fixes what makes it hard to read: the thin outline, the V-shaped bar that crosses the legs, and the detail that disappears at 16 px.

- Solid royal-blue shield with a knocked-out A and a gold crossbar. Same palette, wordmark and lockup box as ADR 0009, so adoption is a drop-in file swap.
- `mark-compact` has a shorter shield and a larger A, tuned for 16–32 px; it stays legible at 16 px.
- Weakness: a shield with a letter is a common compliance cliché, and it says nothing specific about this product.

## B · Layers: meaning (`b-layers/`)

Shows how the tool works. Nested chevrons form an A, and each layer is one level of the answer model (package default, family, product, configuration), with the gold core as the most specific answer. It also reads as a mountain or a sequence of stacked requirements.

- The full mark uses four layers; `mark-compact` and `mark-mono` use three heavier ones, because four thin layers turn into hatching below about 24 px.
- Same blue and gold as today, plus two tints of the blue. Wordmark unchanged.
- Weakness: the idea only lands once someone explains it, and the one-colour version is plain.

## C · Matrix: full redesign from the product description (`c-matrix/`)

Started from the product description only: a tool that works out which regulations apply and then runs risk assessments. A 3×3 grid is both a risk matrix and an applicability table. The shading runs from low (bottom left) to high (top right), and one orange cell stands for the item that needs attention.

- New palette: teal ramp, orange accent, ink `#0F2A33` (reversed on ink, not on blue). New lowercase wordmark in Outfit 600 (SIL Open Font License 1.1; keep the licence file when the font is outlined or bundled).
- Proposed tokens (not applied to the CSS): `--brand-ink #0F2A33`, teal ramp `#D5EEEA #A3DBD3 #5FBDB3 #2A8F8C`, accent `#F2711C` (`#FF9A4D` on dark).
- Weakness: it breaks with the current blue and gold, so the whole site theme would change. The 16 px version reads as a coloured grid, not as a distinct shape.

## Comparison

| | Aim | Fits ADR 0009 palette | Effort to adopt | Small-size result |
|---|---|---|---|---|
| A | Legibility | yes | file swap | best |
| B | Meaning | yes (two added tints) | file swap | good with compact mark |
| C | Fresh identity | no | new tokens and theme | acceptable |

## Adopting one

1. Copy the chosen files into `static/img/`, keeping the existing names (`aavistin-mark.svg`, `aavistin-mark-reversed.svg`, `aavistin-lockup-horizontal.svg`, `aavistin-lockup-horizontal-reversed.svg`). Use `mark-compact` for the favicon in `templates/base.html`.
2. Amend ADR 0009 with the new mark, and for C the new colour tokens and the OFL note for the wordmark font.
3. For C only, update the CSS variables for brand colour and dark mode.
4. Delete the proposals that were not chosen.
