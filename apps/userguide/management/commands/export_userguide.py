import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template.loader import render_to_string

from apps.userguide.services import list_pages, render_page

STATIC_DIR = Path(settings.BASE_DIR) / "static"


def _relative_link_for(slug: str) -> str:
    return f"../{slug}/"


class Command(BaseCommand):
    help = (
        "Render the User Guide (docs/userguide/*.md) to a static site for "
        "GitHub Pages -- the same content and rendering as the in-app "
        "pages, see apps.userguide.services."
    )

    def add_arguments(self, parser):
        parser.add_argument("--output", default="_site", help="Output directory (default: _site).")

    def handle(self, output, **options):
        out_dir = Path(output)
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)

        pages = list_pages()

        (out_dir / "index.html").write_text(
            render_to_string(
                "userguide/static_page.html",
                {"title": "User Guide", "pages": pages, "static_prefix": "", "page_slug": None},
            )
        )

        for entry in pages:
            page = render_page(entry["slug"], link_for=_relative_link_for)
            page_dir = out_dir / page.slug
            page_dir.mkdir()
            (page_dir / "index.html").write_text(
                render_to_string(
                    "userguide/static_page.html",
                    {
                        "title": page.title,
                        "pages": pages,
                        "content_html": page.html,
                        "static_prefix": "../",
                        "page_slug": page.slug,
                    },
                )
            )

        shutil.copytree(STATIC_DIR / "css", out_dir / "static" / "css")
        shutil.copytree(STATIC_DIR / "img", out_dir / "static" / "img")

        self.stdout.write(self.style.SUCCESS(f"Exported {len(pages)} pages to {out_dir}/"))
