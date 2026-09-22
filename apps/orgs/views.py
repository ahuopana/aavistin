from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from .services import visible_organisations


@login_required
def organisation_list(request):
    organisations = visible_organisations(request.user)
    return render(request, "orgs/organisation_list.html", {"organisations": organisations})


@login_required
def organisation_detail(request, slug):
    organisation = get_object_or_404(visible_organisations(request.user), slug=slug)
    return render(
        request,
        "orgs/organisation_detail.html",
        {
            "organisation": organisation,
            "product_families": organisation.product_families.all(),
        },
    )
