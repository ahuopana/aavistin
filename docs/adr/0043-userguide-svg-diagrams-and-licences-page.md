# 43. User Guide diagrams as inline SVG, and a generated Licences page

Status: Accepted

## Context

The User Guide drew its four diagrams from Mermaid blocks, rendered in the browser by a vendored 2.7 MB library. That had three costs: the diagrams did not follow the project's palette and fonts (Mermaid has its own theme), the guide needed JavaScript to show a picture, and the Mermaid file was the largest thing in the repository. The guide also had no page stating Aavistin's licence or those of the software it ships, and a hand-written list would go stale with every dependency change.

`docs/architecture.md` says nothing about either.

## Decision

**Diagrams.**

- Each diagram is an SVG file in `docs/userguide/images/`, referenced from the Markdown as `![alt](images/name.svg)`. Files are hand-laid-out, use the class names `d-box`, `d-key`, `d-title`, `d-line` and so on, and carry their own `<title>` and `<desc>`.
- The renderer inlines the file into the page after the Markdown has been sanitised, and sanitises the SVG itself with `nh3` and an allow-list (shapes, text and markers only: no scripts, styles, links or images). Inlining, rather than `<img>`, is what lets the diagram use the page's CSS variables and follow the light/dark switch, including the manual toggle.
- The colour rules live in `static/css/base.css` (`svg.diagram ...`) and use the design tokens of ADR 0009 and 0030. Each SVG also carries a `<style>` block with the same rules and the token values as fallbacks, only so the file looks right when opened on its own (for example in GitHub's file view). It is stripped when the file is inlined.
- Other images in guide Markdown are not supported and render as their alt text.
- Mermaid is removed from the User Guide, the static export and `static/vendor/`. Mermaid in `docs/architecture.md` stays: it is read on GitHub, which renders it.

**Licences page.**

- `apps/userguide/licenses.py` builds a generated page, `licences`, listed after the Markdown pages and rendered through the same pipeline, so it appears in the app and in the GitHub Pages export.
- Python dependencies are the runtime closure of `[project].dependencies` in `pyproject.toml`, resolved against installed package metadata (`License-Expression`, then licence classifiers, then a short `License` field). Development tools are not listed. Nothing is maintained by hand, and a package with no stated licence is shown as such rather than hidden.
- Front-end libraries and fonts have no package metadata, so they are listed in `static/vendor/manifest.json`. A test fails if a file is added to `static/vendor/` without an entry.
- The Pages workflow also runs when `pyproject.toml`, `uv.lock`, `LICENSE` or the manifest change.
- `packaging` is now a declared dependency (it was already installed through other packages).

## Consequences

- The guide works without JavaScript.
- Changing a diagram means editing SVG coordinates by hand. The files are small and the structure is regular, but there is no diagram-as-text source any more.
- The licence expressions are whatever each package declares. They are not legal review, and the page says the licence texts ship with each package.
- While correcting the manifest, `htmx` 2.x turned out to be 0BSD, not MIT as `static/vendor/README.md` had said; the manifest is now the single source for these facts.
