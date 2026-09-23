from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from .services import list_pages, render_page


def _link_for(slug: str) -> str:
    return reverse("userguide:page", args=[slug])


def index(request):
    pages = list_pages()
    return render(request, "userguide/index.html", {"pages": pages})


def page(request, slug):
    pages = list_pages()
    try:
        current = render_page(slug, link_for=_link_for)
    except KeyError:
        raise Http404(f"No user guide page '{slug}'") from None
    return render(request, "userguide/page.html", {"pages": pages, "page": current})
