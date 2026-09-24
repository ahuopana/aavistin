from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, render

from apps.products.models import Product, ProductStatus
from apps.products.services import editable_product_families

from .models import ProductFamily
from .services import visible_organisations


@login_required
def portfolio(request):
    """Product-first landing page: product families flattened across organisations.

    Organisation is shown as a small caption on each family, not a level
    you have to click through -- see the product families' own
    organisation membership without organisation being "a big deal".
    """
    families = (
        ProductFamily.objects.filter(organisation__in=visible_organisations(request.user))
        .select_related("organisation")
        .prefetch_related(
            Prefetch(
                "products",
                queryset=Product.objects.exclude(status=ProductStatus.DELETED),
                to_attr="visible_products",
            )
        )
        .order_by("organisation__name", "name")
    )
    editable_family_ids = set(editable_product_families(request.user).values_list("id", flat=True))
    return render(
        request,
        "orgs/portfolio.html",
        {"families": families, "editable_family_ids": editable_family_ids},
    )


@login_required
def organisation_list(request):
    organisations = visible_organisations(request.user)
    return render(request, "orgs/organisation_list.html", {"organisations": organisations})


@login_required
def organisation_detail(request, slug):
    organisation = get_object_or_404(visible_organisations(request.user), slug=slug)
    editable_family_ids = set(editable_product_families(request.user).values_list("id", flat=True))
    return render(
        request,
        "orgs/organisation_detail.html",
        {
            "organisation": organisation,
            "product_families": organisation.product_families.all(),
            "editable_family_ids": editable_family_ids,
        },
    )
