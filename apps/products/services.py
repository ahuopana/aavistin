"""Product-level authoring: permission scoping, approval and delete protection.

Kept separate from models.py and views.py, matching the pattern in
apps.orgs.services / apps.assessments.services: read-side scoping queries
and small write-side rules, not persistence or request handling.
"""

from django.db.models import Q
from django.utils import timezone

from apps.orgs.models import ProductFamily, Role, RoleAssignment

from .models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareOption,
    SoftwareRelease,
)


class ApprovedEntityError(Exception):
    """Raised when trying to delete an entity that has already been approved."""


def product_of(instance) -> Product:
    """Resolve the owning Product for any product-level-and-below entity."""
    if isinstance(instance, Product):
        return instance
    if isinstance(instance, HardwareVariant):
        return instance.product
    if isinstance(instance, HardwareRevision):
        return instance.hardware_variant.product
    if isinstance(instance, SoftwareRelease):
        return instance.product
    if isinstance(instance, SoftwareOption):
        return instance.software_release.product
    if isinstance(instance, Configuration):
        return instance.hardware_revision.hardware_variant.product
    raise TypeError(f"Not a product-level entity: {instance!r}")


def approve(instance, *, actor):
    instance.is_approved = True
    instance.approved_at = timezone.now()
    instance.approved_by = actor
    instance.save(update_fields=["is_approved", "approved_at", "approved_by"])


def delete_entity(instance):
    if instance.is_approved:
        raise ApprovedEntityError(f"{instance} is approved and cannot be deleted.")
    instance.delete()


def _grantee_filter(user):
    group_ids = list(user.groups.values_list("id", flat=True))
    grantee_filter = Q(user=user)
    if group_ids:
        grantee_filter |= Q(group_id__in=group_ids)
    return grantee_filter


def editable_product_families(user, role: str = Role.EDITOR):
    """ProductFamily objects where ``user`` holds ``role``, inherited from its organisation."""
    if not user.is_authenticated:
        return ProductFamily.objects.none()
    if user.is_superuser:
        return ProductFamily.objects.all()

    role_filter = Q(role=role) & _grantee_filter(user)
    org_ids = RoleAssignment.objects.filter(role_filter, organisation__isnull=False).values_list(
        "organisation_id", flat=True
    )
    family_ids = RoleAssignment.objects.filter(
        role_filter, product_family__isnull=False
    ).values_list("product_family_id", flat=True)
    return ProductFamily.objects.filter(
        Q(organisation_id__in=org_ids) | Q(id__in=family_ids)
    ).distinct()


def editable_products(user, role: str = Role.EDITOR):
    """Product objects where ``user`` holds ``role``, at any scope in its hierarchy."""
    if not user.is_authenticated:
        return Product.objects.none()
    if user.is_superuser:
        return Product.objects.all()

    role_filter = Q(role=role) & _grantee_filter(user)
    product_ids = RoleAssignment.objects.filter(role_filter, product__isnull=False).values_list(
        "product_id", flat=True
    )
    families = editable_product_families(user, role=role)
    return Product.objects.filter(
        Q(product_family__in=families) | Q(id__in=product_ids)
    ).distinct()
