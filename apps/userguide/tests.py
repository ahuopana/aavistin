import re
import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from packaging.utils import canonicalize_name

from . import licenses, services
from .services import list_pages, render_page


class MarkdownFixture(TestCase):
    """Points apps.userguide.services at a throwaway docs/userguide
    directory instead of the real one, so these tests exercise the
    rendering logic without depending on the real guide's prose.
    """

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmpdir.name)
        self._patcher = mock.patch.object(services, "USERGUIDE_DIR", self.dir)
        self._patcher.start()
        self._generated = mock.patch.dict(services.GENERATED_PAGES, clear=True)
        self._generated.start()
        services._known_slugs.cache_clear()

    def tearDown(self):
        self._generated.stop()
        self._patcher.stop()
        services._known_slugs.cache_clear()
        self._tmpdir.cleanup()

    def _write(self, filename: str, content: str):
        (self.dir / filename).write_text(content)


class ListPagesTests(MarkdownFixture):
    def test_orders_by_filename_prefix(self):
        self._write("02-second.md", "# Second\n\nBody.\n")
        self._write("01-first.md", "# First\n\nBody.\n")
        self.assertEqual(
            [p["slug"] for p in list_pages()],
            ["first", "second"],
        )

    def test_title_comes_from_leading_h1(self):
        self._write("01-a.md", "# A Real Title\n\nBody.\n")
        self.assertEqual(list_pages(), [{"slug": "a", "title": "A Real Title"}])

    def test_ignores_files_without_a_numeric_prefix(self):
        self._write("readme.md", "# Not a page\n")
        self._write("01-a.md", "# A\n\nBody.\n")
        self.assertEqual([p["slug"] for p in list_pages()], ["a"])


class RenderPageTests(MarkdownFixture):
    def test_missing_title_falls_back_to_slug(self):
        self._write("01-a.md", "Just a paragraph, no heading.\n")
        page = render_page("a")
        self.assertEqual(page.title, "a")
        self.assertIn("Just a paragraph", page.html)

    def test_unknown_slug_raises_key_error(self):
        with self.assertRaises(KeyError):
            render_page("does-not-exist")

    def test_script_tags_are_stripped(self):
        self._write("01-a.md", "# A\n\nHello <script>alert(1)</script> world.\n")
        page = render_page("a")
        self.assertNotIn("<script", page.html)
        self.assertNotIn("alert(1)", page.html)

    def test_diagram_image_is_inlined_as_sanitised_svg(self):
        (self.dir / "images").mkdir()
        (self.dir / "images" / "flow.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" role="img">'
            "<title>T</title><style>*{display:none}</style><script>alert(1)</script>"
            '<rect class="d-box" x="1" y="1" width="8" height="8" rx="2" onclick="x()"/>'
            '<a href="javascript:alert(1)"><text x="2" y="5">hi</text></a></svg>'
        )
        self._write("01-a.md", "# A\n\n![A flow](images/flow.svg)\n")
        html = render_page("a").html
        self.assertIn('<div class="diagram"><svg', html)
        self.assertIn('viewBox="0 0 10 10"', html)
        self.assertIn('<rect class="d-box"', html)
        for unsafe in ("<script", "alert(1)", "onclick", "<style", "javascript:", "<a "):
            self.assertNotIn(unsafe, html)
        self.assertNotIn("@@diagram", html)

    def test_missing_diagram_falls_back_to_alt_text(self):
        self._write("01-a.md", "# A\n\n![Not there](images/nope.svg)\n")
        html = render_page("a").html
        self.assertIn("Not there", html)
        self.assertNotIn("<svg", html)

    def test_other_images_are_not_rendered(self):
        self._write("01-a.md", "# A\n\n![Tracker](https://example.com/x.png)\n")
        html = render_page("a").html
        self.assertNotIn("<img", html)
        self.assertNotIn("example.com", html)

    def test_code_fences_keep_no_class(self):
        self._write("01-a.md", '# A\n\n```python\nprint(1)\n```\n\n<p class="x">x</p>\n')
        html = render_page("a").html
        self.assertIn("print(1)", html)
        self.assertNotIn('class="x"', html)

    def test_known_internal_link_is_rewritten(self):
        self._write("01-a.md", "# A\n\nSee [B](b).\n")
        self._write("02-b.md", "# B\n\nBody.\n")
        page = render_page("a", link_for=lambda slug: f"/guide/{slug}/")
        self.assertIn('href="/guide/b/"', page.html)

    def test_external_link_is_left_alone(self):
        self._write("01-a.md", "# A\n\nSee [external](https://example.com).\n")
        page = render_page("a", link_for=lambda slug: f"/guide/{slug}/")
        self.assertIn('href="https://example.com"', page.html)

    def test_default_link_for_leaves_bare_slug(self):
        self._write("01-a.md", "# A\n\nSee [B](b).\n")
        self._write("02-b.md", "# B\n\nBody.\n")
        page = render_page("a")
        self.assertIn('href="b"', page.html)


class ViewTests(TestCase):
    """Against the real docs/userguide content -- structural checks only,
    so these don't break if the guide's prose is edited.
    """

    def test_index_requires_no_login(self):
        response = self.client.get(reverse("userguide:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Guide")

    def test_index_lists_every_page(self):
        response = self.client.get(reverse("userguide:index"))
        for entry in list_pages():
            self.assertContains(response, entry["title"])

    def test_page_view_renders_selected_page(self):
        first = list_pages()[0]
        response = self.client.get(reverse("userguide:page", args=[first["slug"]]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first["title"])

    def test_unknown_slug_is_404(self):
        response = self.client.get(reverse("userguide:page", args=["does-not-exist"]))
        self.assertEqual(response.status_code, 404)


class RealGuideTests(TestCase):
    """Against the real docs/userguide content."""

    def test_every_page_renders_without_leftover_diagram_placeholders(self):
        for entry in list_pages():
            html = render_page(entry["slug"]).html
            self.assertNotIn("@@diagram", html, entry["slug"])

    def test_every_diagram_file_is_used_by_a_page_and_every_use_resolves(self):
        used = set()
        for path in services.USERGUIDE_DIR.glob("*.md"):
            used |= set(re.findall(r"\]\(images/([a-z0-9-]+)\.svg\)", path.read_text()))
        on_disk = {p.stem for p in (services.USERGUIDE_DIR / "images").glob("*.svg")}
        self.assertEqual(used, on_disk)

    def test_workflow_page_has_its_diagrams_inline(self):
        html = render_page("workflow").html
        self.assertEqual(html.count('<div class="diagram">'), 4)
        # Colours come from the page's CSS, not from the file.
        self.assertNotIn("<style", html)

    def test_diagram_files_are_self_contained(self):
        for path in (services.USERGUIDE_DIR / "images").glob("*.svg"):
            text = path.read_text()
            self.assertNotRegex(text, r"<script|<image|<foreignObject|href=|@import", path.name)
            self.assertIn("<title", text, path.name)
            self.assertIn("<desc", text, path.name)


class LicencesPageTests(TestCase):
    def test_page_is_listed_last_and_needs_no_login(self):
        self.assertEqual(list_pages()[-1], {"slug": "licences", "title": "Licences"})
        response = self.client.get(reverse("userguide:page", args=["licences"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "GNU Affero General Public License")

    def test_license_file_is_the_one_the_page_names(self):
        text = (Path(settings.BASE_DIR) / "LICENSE").read_text()
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", text)
        self.assertIn("Version 3", text)

    def test_lists_direct_and_indirect_dependencies_with_licences(self):
        deps = {d.name.lower(): d for d in licenses.python_dependencies()}
        self.assertTrue(deps["django"].direct)
        self.assertEqual(deps["django"].license, "BSD-3-Clause")
        self.assertFalse(deps["asgiref"].direct)  # pulled in by Django
        # Direct dependencies come first.
        flags = [d.direct for d in licenses.python_dependencies()]
        self.assertEqual(flags, sorted(flags, reverse=True))

    def test_development_tools_are_not_listed(self):
        names = {d.name.lower() for d in licenses.python_dependencies()}
        self.assertNotIn("pytest", names)
        self.assertNotIn("ruff", names)

    def test_every_declared_dependency_is_listed(self):
        declared = {canonicalize_name(r.name) for r in licenses._declared_requirements()}
        listed = {canonicalize_name(d.name) for d in licenses.python_dependencies()}
        self.assertLessEqual(declared, listed)

    def test_every_vendored_file_has_a_manifest_entry(self):
        vendor = Path(settings.BASE_DIR) / "static" / "vendor"
        files = {p.name for p in vendor.glob("*.js")}
        listed = {entry["file"] for entry in licenses.vendored_manifest()["libraries"]}
        self.assertEqual(files, listed)

    def test_vendored_libraries_and_fonts_appear_on_the_page(self):
        html = render_page("licences").html
        for entry in licenses.vendored_manifest()["libraries"]:
            self.assertIn(entry["name"], html)
        self.assertIn("Outfit", html)

    def test_table_cells_cannot_break_the_table(self):
        self.assertEqual(licenses._cell("a | b\nc"), "a \\| b c")


class ExportCommandTests(TestCase):
    def test_export_writes_index_and_one_dir_per_page(self):
        with tempfile.TemporaryDirectory() as out:
            output_dir = Path(out) / "site"
            call_command("export_userguide", output=str(output_dir))

            self.assertTrue((output_dir / "index.html").exists())
            self.assertTrue((output_dir / "static" / "css" / "base.css").exists())

            pages = list_pages()
            self.assertTrue(pages)
            for entry in pages:
                page_file = output_dir / entry["slug"] / "index.html"
                self.assertTrue(page_file.exists(), page_file)

    def test_exported_pages_inline_diagrams_and_need_no_script(self):
        with tempfile.TemporaryDirectory() as out:
            output_dir = Path(out) / "site"
            call_command("export_userguide", output=str(output_dir))

            content = (output_dir / "workflow" / "index.html").read_text()
            self.assertIn('<div class="diagram"><svg', content)
            self.assertNotIn("<script", content)
            self.assertFalse((output_dir / "static" / "vendor").exists())
            self.assertTrue((output_dir / "licences" / "index.html").exists())

    def test_internal_links_are_relative_in_exported_pages(self):
        with tempfile.TemporaryDirectory() as out:
            output_dir = Path(out) / "site"
            call_command("export_userguide", output=str(output_dir))

            first = list_pages()[0]
            content = (output_dir / first["slug"] / "index.html").read_text()
            # Every href to another guide page must be a relative
            # "../<slug>/" link, not an absolute in-app "/guide/..." one --
            # the static export has no Django server behind it.
            self.assertNotIn('href="/guide/', content)
