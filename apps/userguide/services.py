"""Renders the User Guide: Markdown files under docs/userguide/, single
-sourced between the in-app pages (apps.userguide.views) and the static
export published to GitHub Pages (apps.userguide.management.commands.
export_userguide). See docs/architecture.md, "User Guide".

Pages are repository content, authored by maintainers, not user input --
but rendered Markdown is still always run through nh3 (CLAUDE.md hard
rule), since a future contributor could paste in something unsafe
without anyone noticing in review.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import mistune
import nh3
from django.conf import settings

USERGUIDE_DIR = Path(settings.BASE_DIR) / "docs" / "userguide"
_FILENAME_RE = re.compile(r"^\d+-(?P<slug>[a-z0-9-]+)\.md$")

ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "strong",
    "em",
    "del",
    "a",
    "code",
    "pre",
    "blockquote",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "input",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "input": {"type", "checked", "disabled"},
}


@dataclass(frozen=True)
class Page:
    slug: str
    title: str
    html: str


class _InternalLinkRenderer(mistune.HTMLRenderer):
    """A link whose target is exactly another guide page's slug (no
    scheme, not a path) is rewritten through ``link_for``; anything else
    -- external URLs, mailto:, in-page anchors -- renders unchanged.
    """

    def __init__(self, *, known_slugs: frozenset[str], link_for):
        super().__init__(escape=False)
        self._known_slugs = known_slugs
        self._link_for = link_for

    def link(self, text: str, url: str, title: str | None = None) -> str:
        if url in self._known_slugs:
            url = self._link_for(url)
        return super().link(text, url, title)


def _page_files() -> list[Path]:
    files = [p for p in USERGUIDE_DIR.glob("*.md") if _FILENAME_RE.match(p.name)]
    return sorted(files, key=lambda p: p.name)


@lru_cache
def _known_slugs() -> frozenset[str]:
    return frozenset(_FILENAME_RE.match(p.name)["slug"] for p in _page_files())


def _extract_title(body: str, *, fallback: str) -> tuple[str, str]:
    """(title, remaining_body) -- the page's title is its leading level-1
    heading, stripped out so it isn't rendered twice (the template shows
    it separately, e.g. as <h1> plus nav highlighting).
    """
    lines = body.lstrip().split("\n", 1)
    first = lines[0].strip()
    if first.startswith("# "):
        return first[2:].strip(), (lines[1] if len(lines) > 1 else "")
    return fallback, body


def _ordered_slugs() -> list[str]:
    return [_FILENAME_RE.match(p.name)["slug"] for p in _page_files()]


def list_pages() -> list[dict]:
    """[{"slug", "title"}, ...] in reading order."""
    return [
        {"slug": page.slug, "title": page.title} for page in map(render_page, _ordered_slugs())
    ]


def render_page(slug: str, *, link_for=None) -> Page:
    """The Page for ``slug``, or raises KeyError if it doesn't exist.

    ``link_for(other_slug) -> str`` decides what an internal link
    renders as; defaults to the bare slug (relied on to be overridden by
    each caller -- the in-app view wants a URL, the static exporter
    wants a relative path). Not cached: parsing a few small Markdown
    files per request is cheap, and ``link_for`` is a fresh closure per
    caller anyway, which would defeat an lru_cache here.
    """
    matches = [p for p in _page_files() if _FILENAME_RE.match(p.name)["slug"] == slug]
    if not matches:
        raise KeyError(slug)

    link_for = link_for or (lambda s: s)
    title, body = _extract_title(matches[0].read_text(), fallback=slug)
    renderer = _InternalLinkRenderer(known_slugs=_known_slugs(), link_for=link_for)
    md = mistune.create_markdown(
        renderer=renderer, plugins=["table", "task_lists", "strikethrough"]
    )
    raw_html = md(body)
    clean_html = nh3.clean(raw_html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
    return Page(slug=slug, title=title, html=clean_html)
