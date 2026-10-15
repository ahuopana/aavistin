"""The generated "Licences" page of the User Guide.

Nothing here is maintained by hand for Python packages: the list is the
runtime dependency closure of ``[project].dependencies`` in
``pyproject.toml``, resolved against the installed distributions'
metadata, so it changes when ``uv lock`` does. Development-only tools
(``[dependency-groups]``) are not walked, because they are not shipped.

The only hand-kept part is ``static/vendor/manifest.json``: the
front-end libraries copied into the repository and the fonts the pages
load, which have no package metadata to read. A test fails if a file is
added under ``static/vendor/`` without an entry there.
"""

import json
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path

from django.conf import settings
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

MAIN_LICENSE_NAME = "GNU Affero General Public License, version 3 (AGPL-3.0)"
MAIN_LICENSE_URL = "https://www.gnu.org/licenses/agpl-3.0.html"
REPOSITORY_URL = "https://github.com/ahuopana/aavistin"

# License text in the ``License`` metadata field is sometimes the whole
# licence; anything longer than this is not a name.
_MAX_LICENSE_FIELD = 60
_UNKNOWN = "Not stated in the package metadata"


@dataclass(frozen=True)
class Dependency:
    name: str
    version: str
    license: str
    url: str
    direct: bool


def _license_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression
    classifiers = [
        c.rsplit("::", 1)[-1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    # "License :: OSI Approved" alone names no licence.
    classifiers = [c for c in classifiers if c != "OSI Approved"]
    if classifiers:
        return ", ".join(classifiers)
    field = " ".join((meta.get("License") or "").split())
    if field and field.upper() != "UNKNOWN" and len(field) <= _MAX_LICENSE_FIELD:
        return field
    return _UNKNOWN


def _url_of(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    candidates = [meta.get("Home-page") or ""]
    for entry in meta.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() in {"homepage", "home", "source", "repository"}:
            candidates.append(url.strip())
    for url in candidates:
        if url.startswith(("https://", "http://")):
            return url
    return ""


def _declared_requirements() -> list[Requirement]:
    pyproject = tomllib.loads((Path(settings.BASE_DIR) / "pyproject.toml").read_text())
    return [Requirement(spec) for spec in pyproject["project"]["dependencies"]]


def _applies(requirement: Requirement, extras: frozenset[str]) -> bool:
    if requirement.marker is None:
        return True
    return any(requirement.marker.evaluate({"extra": extra}) for extra in extras | {""})


@lru_cache
def python_dependencies() -> tuple[Dependency, ...]:
    """Direct dependencies first, then the rest, each sorted by name."""
    direct = {canonicalize_name(r.name) for r in _declared_requirements()}
    seen: dict[str, Dependency] = {}
    queue = [(r, frozenset(r.extras)) for r in _declared_requirements()]
    while queue:
        requirement, extras = queue.pop()
        key = canonicalize_name(requirement.name)
        if key in seen:
            continue
        try:
            dist = metadata.distribution(requirement.name)
        except metadata.PackageNotFoundError:
            continue
        seen[key] = Dependency(
            name=dist.metadata["Name"],
            version=dist.version,
            license=_license_of(dist),
            url=_url_of(dist),
            direct=key in direct,
        )
        for sub in dist.requires or []:
            parsed = Requirement(sub)
            if _applies(parsed, extras):
                queue.append((parsed, frozenset(parsed.extras)))
    return tuple(sorted(seen.values(), key=lambda d: (not d.direct, d.name.lower())))


@lru_cache
def vendored_manifest() -> dict:
    path = Path(settings.BASE_DIR) / "static" / "vendor" / "manifest.json"
    return json.loads(path.read_text())


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _link(text: str, url: str) -> str:
    return f"[{_cell(text)}]({url})" if url else _cell(text)


def _table(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def licenses_markdown() -> str:
    deps = python_dependencies()
    manifest = vendored_manifest()

    def python_rows(direct: bool) -> list[tuple[str, ...]]:
        return [
            (_link(d.name, d.url), _cell(d.version), _cell(d.license))
            for d in deps
            if d.direct is direct
        ]

    header = ("Package", "Version", "Licence")
    return "\n".join(
        [
            "This page is generated from the installed software, so it is always the",
            "list of what this copy of Aavistin actually ships with.",
            "",
            "## Aavistin",
            "",
            f"Aavistin is free software, released under the **{MAIN_LICENSE_NAME}**.",
            "The full text is in the `LICENSE` file at the root of the",
            f"[source repository]({REPOSITORY_URL}) and at",
            f"[gnu.org]({MAIN_LICENSE_URL}). Regulation content in `packages/` is",
            "written as own summaries with references; it does not reproduce text from",
            "standards.",
            "",
            "## Python dependencies",
            "",
            "Each dependency is used under its own licence, shown below as the package",
            "declares it. The licence text itself is included in each installed package.",
            "Tools used only for development and testing are not listed, because they",
            "are not part of what is shipped.",
            "",
            "### Direct dependencies",
            "",
            _table(header, python_rows(True)),
            "",
            "### Indirect dependencies",
            "",
            "Packages that the dependencies above need in turn.",
            "",
            _table(header, python_rows(False)),
            "",
            "## Front-end libraries",
            "",
            "Copied unmodified into `static/vendor/` and served from the same origin.",
            "",
            _table(
                ("Library", "Version", "Licence"),
                [
                    (_link(e["name"], e.get("url", "")), _cell(e["version"]), _cell(e["license"]))
                    for e in manifest["libraries"]
                ],
            ),
            "",
            "## Fonts and artwork",
            "",
            _table(
                ("Item", "Used for", "Licence"),
                [
                    (_link(e["name"], e.get("url", "")), _cell(e["used_for"]), _cell(e["license"]))
                    for e in manifest["fonts_and_artwork"]
                ],
            ),
            "",
        ]
    )
