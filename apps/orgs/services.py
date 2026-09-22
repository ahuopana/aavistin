"""Role and separation-of-duties resolution.

Kept separate from models.py: these are read-side queries over
RoleAssignment / SoDPolicy, not persistence concerns.
"""

from django.db.models import Q

from .models import Organisation, ProductFamily, RoleAssignment, SoDPolicy


def roles_for_user(user, *, organisation=None, product_family=None) -> set[str]:
    """Roles ``user`` holds at the given scope, inherited from ancestors.

    Pass exactly one of ``organisation`` or ``product_family``. A grant on
    an ancestor (organisation, for a product_family scope) is included.
    """
    if bool(organisation) == bool(product_family):
        raise ValueError("Pass exactly one of organisation or product_family.")

    if not user.is_authenticated:
        return set()

    if product_family is not None:
        scope_filter = Q(organisation=product_family.organisation) | Q(
            product_family=product_family
        )
    else:
        scope_filter = Q(organisation=organisation)

    group_ids = list(user.groups.values_list("id", flat=True))
    grantee_filter = Q(user=user)
    if group_ids:
        grantee_filter |= Q(group_id__in=group_ids)

    qs = RoleAssignment.objects.filter(scope_filter).filter(grantee_filter)
    return set(qs.values_list("role", flat=True))


def has_role(user, role: str, *, organisation=None, product_family=None) -> bool:
    return role in roles_for_user(user, organisation=organisation, product_family=product_family)


def visible_organisations(user):
    """Organisations where ``user`` holds any role, directly or via a family."""
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
    direct_ids = Organisation.objects.filter(grantee_filter).values_list("id", flat=True)

    return Organisation.objects.filter(Q(id__in=direct_ids) | Q(id__in=family_org_ids)).distinct()


def effective_sod_policy(*, organisation=None, product_family=None) -> str:
    if product_family is not None:
        return product_family.effective_sod_policy
    if organisation is not None:
        return organisation.sod_policy
    return SoDPolicy.WARN
