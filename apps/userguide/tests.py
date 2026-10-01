import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from . import services
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
        services._known_slugs.cache_clear()

    def tearDown(self):
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
