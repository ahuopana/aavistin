# 12. User Guide: single-sourced Markdown, in-app and GitHub Pages

Status: Accepted

## Context

Aavistin needed its own product documentation — a user guide, not the "Documents" system in `docs/architecture.md` (which is for user-authored content with optimistic locking and revision history) and not the per-organisation wiki requested alongside it (a distinct, separate, not-yet-designed feature — see "Open questions" in `docs/architecture.md`). The ask was for the guide to be readable both inside the app and, optionally, published to GitHub Pages, from one source rather than two copies that drift.

## Decisions

- **Plain Markdown files in the repo (`docs/userguide/NN-slug.md`), not a database model.** The guide is maintainer-authored and versioned with the code, like the rest of the documentation — it doesn't need edit locking, revision history or per-viewer state, so giving it a model and admin UI would be solving a problem it doesn't have. The `NN-` prefix sets reading order without a separate ordering field to keep in sync; the slug after it is the URL and the target other pages link to.
- **The title lives in the document, not in config.** A page's title is its leading `# H1`, extracted at render time rather than duplicated into a manifest — one place to get it right, and a new page needs no registration beyond adding the file.
- **`mistune` for Markdown → HTML.** `docs/architecture.md`'s "Documents and concurrent editing" section already named `markdown-it-py` or `mistune` for a heavier, editor-integrated rendering path; for a static, repo-authored corpus with no round-trip-with-a-JS-editor requirement, `mistune` (pure Python, no extra runtime dependency) was the simpler of the two with no coupling reason to prefer the other.
- **Always sanitized with `nh3`, no exception for "trusted" maintainer content.** CLAUDE.md's hard rule doesn't carve out an exception, and a future contributor could still introduce something unsafe without it being caught in review — sanitizing unconditionally costs nothing here and removes the judgment call.
- **Single-sourced internal links via a custom renderer, not two Markdown trees.** A link `[text](other-page)` is only rewritten when `other-page` matches exactly another guide page's slug; the same Markdown renders correctly in-app (`link_for` produces an in-app URL) and in the static export (`link_for` produces a relative `../<slug>/` path) without maintaining separate content or a link-rewriting pass bolted on afterward.
- **The in-app guide needs no login.** Someone evaluating Aavistin before creating an account should still be able to read how it works; the guide carries no product data, so there's nothing to protect.
- **The static export is a management command (`export_userguide`), not a separate app or build tool.** It reuses `apps.userguide.services` directly — same parsing, same sanitization — and is driven by a GitHub Actions workflow (`.github/workflows/pages.yml`) using `actions/upload-pages-artifact` + `actions/deploy-pages`, matching the project's "no Node build" stance (the export is Python, and the static output needs no JS build step of its own).

## Consequences

- Adding a guide page is: add `docs/userguide/NN-slug.md`, done — no migration, no admin registration, no second copy to keep current for GitHub Pages.
- Enabling the GitHub Pages publish itself needs a one-time manual step by a repository admin (Settings → Pages → Source: GitHub Actions) — no API available to a workflow file or this session to turn that on remotely; until then the workflow will build successfully but the deploy step has nothing to deploy to.
- The static export intentionally does not reuse `templates/base.html` (which assumes a live Django request — auth state, `{% url %}` targets that don't exist in a static context). `templates/userguide/static_page.html` is a second, minimal template kept visually consistent by reusing the same CSS file and class names, not by sharing template code — if the app shell's markup changes significantly, this template needs a matching update, caught by comparing the two live (there's no automated visual-diff check for that yet).
