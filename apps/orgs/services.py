"""Role and separation-of-duties resolution.

Kept separate from models.py: these are read-side queries over
RoleAssignment / SoDPolicy, not persistence concerns.
"""

from django.db.models import Q
from django.http import Http404
from django.urls import reverse

from .models import Organisation, ProductFamily, RoleAssignment, SoDPolicy


def roles_for_user(user, *, organisation=None, product_family=None, product=None) -> set[str]:
    """Roles ``user`` holds at the given scope, inherited from ancestors.

    Pass exactly one of ``organisation``, ``product_family`` or
    ``product``. A grant on an ancestor scope is included (e.g. an
    organisation-level grant is visible at every product_family and
    product beneath it).
    """
    scopes = (organisation, product_family, product)
    if sum(s is not None for s in scopes) != 1:
        raise ValueError("Pass exactly one of organisation, product_family or product.")

    if product is not None:
        family = product.product_family
        scope_filter = (
            Q(organisation=family.organisation) | Q(product_family=family) | Q(product=product)
        )
    elif product_family is not None:
        scope_filter = Q(organisation=product_family.organisation) | Q(
            product_family=product_family
        )
    else:
        scope_filter = Q(organisation=organisation)

    if not user.is_authenticated:
        return set()

    group_ids = list(user.groups.values_list("id", flat=True))
    grantee_filter = Q(user=user)
    if group_ids:
        grantee_filter |= Q(group_id__in=group_ids)

    qs = RoleAssignment.objects.filter(scope_filter).filter(grantee_filter)
    return set(qs.values_list("role", flat=True))


def has_role(user, role: str, **scope) -> bool:
    return role in roles_for_user(user, **scope)


def can_view_product(user, product) -> bool:
    """Read access: a superuser, or anyone holding any role that reaches ``product``
    (directly, or inherited from its family or organisation)."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or bool(roles_for_user(user, product=product))


def require_product_view(user, product):
    """Return ``product``, or raise ``Http404`` when ``user`` may not see it.

    404 rather than a redirect or 403, so product ids can't be probed for existence.
    """
    if not can_view_product(user, product):
        raise Http404("Not found.")
    return product


def visible_organisations(user):
    """Organisations where ``user`` holds any role, at any scope level."""
    if not user.is_authenticated:
        return Organisation.objects.none()
    if user.is_superuser:
        return Organisation.objects.all()

    group_ids = list(user.groups.values_list("id", flat=True))
    grantee_filter = Q(role_assignments__user=user)
    if group_ids:
        grantee_filter |= Q(role_assignments__group_id__in=group_ids)

    family_org_ids = (
        ProductFamily.objects.filter(grantee_filter)
        .values_list("organisation_id", flat=True)
        .distinct()
    )
    from apps.products.models import Product

    product_org_ids = (
        Product.objects.filter(grantee_filter)
        .values_list("product_family__organisation_id", flat=True)
        .distinct()
    )
    direct_ids = Organisation.objects.filter(grantee_filter).values_list("id", flat=True)

    return Organisation.objects.filter(
        Q(id__in=direct_ids) | Q(id__in=family_org_ids) | Q(id__in=product_org_ids)
    ).distinct()


def effective_sod_policy(*, organisation=None, product_family=None) -> str:
    if product_family is not None:
        return product_family.effective_sod_policy
    if organisation is not None:
        return organisation.sod_policy
    return SoDPolicy.WARN


def role_grants_for_user(user) -> list[dict]:
    """Every grant that gives ``user`` a role, direct or through a group.

    One row per RoleAssignment, with a human label for the scope and the page
    to open it (organisations and products have pages; a family links to its
    anchor on the portfolio). Ordered by scope breadth, then name.
    """
    if not user.is_authenticated:
        return []
    group_ids = list(user.groups.values_list("id", flat=True))
    grantee = Q(user=user)
    if group_ids:
        grantee |= Q(group_id__in=group_ids)
    assignments = (
        RoleAssignment.objects.filter(grantee)
        .select_related(
            "group", "organisation", "product_family__organisation", "product__product_family"
        )
        .order_by("id")
    )

    rows = []
    for a in assignments:
        if a.organisation_id:
            scope, label = "Organisation", a.organisation.name
            url = reverse("orgs:detail", args=[a.organisation.slug])
            rank = 0
        elif a.product_family_id:
            scope, label = "Product family", a.product_family.name
            url = reverse("orgs:portfolio") + f"#family-{a.product_family_id}"
            rank = 1
        else:
            scope, label = "Product", str(a.product)
            url = reverse("products:product_detail", args=[a.product_id])
            rank = 2
        rows.append(
            {
                "role": a.get_role_display(),
                "scope": scope,
                "target": label,
                "url": url,
                "via": f"Group {a.group.name}" if a.group_id else "Directly",
                "_sort": (rank, label.lower(), a.role),
            }
        )
    rows.sort(key=lambda r: r["_sort"])
    for r in rows:
        del r["_sort"]
    return rows
