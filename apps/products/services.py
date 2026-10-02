"""Product-level authoring: permission scoping, approval and delete protection.

Kept separate from models.py and views.py, matching the pattern in
apps.orgs.services / apps.assessments.services: read-side scoping queries
and small write-side rules, not persistence or request handling.
"""

from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.assessments.evaluation import evaluate_configuration
from apps.orgs.models import ProductFamily, Role, RoleAssignment
from apps.risk.models import EntryType, RiskEntry
from apps.risk.rating import evaluate_residual_rating

from .models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    ProductStatus,
    SoftwareOption,
    SoftwareRelease,
)

ACCEPTABLE_RESIDUAL_RATINGS = ("accept", "justify")


def compliance_ratio(product) -> tuple[int, int]:
    """(fulfilled, total) in-scope requirements across the product's
    configurations' current evaluation (live, not frozen to an approved
    snapshot). A requirement counts as fulfilled unless its package has
    an unresolved action-required finding in that evaluation -- findings
    aren't tracked per requirement, only per package, so this is a
    package-level proxy, not a true per-requirement pass/fail.
    """
    total: set[tuple[str, str, str]] = set()
    bad: set[tuple[str, str, str]] = set()

    configurations = Configuration.objects.filter(
        hardware_revision__hardware_variant__product=product
    )
    for configuration in configurations:
        evaluation = evaluate_configuration(configuration)
        blocking_packages = {
            (f["source"], f["version"])
            for f in evaluation["findings"]
            if f["level"] == "action_required"
        }
        for result in evaluation["results"]:
            if not result["in_scope"]:
                continue
            package_key = (result["source"], result["version"])
            for requirement_id in result["requirements"]:
                key = (*package_key, requirement_id)
                total.add(key)
                if package_key in blocking_packages:
                    bad.add(key)

    return len(total - bad), len(total)


def risk_ratio(product) -> tuple[int, int]:
    """(acceptable, total) baseline threat/hazard entries, where
    "acceptable" means every method treatment on the entry has a
    residual acceptance of "accept" or "justify" -- an entry with no
    treatment yet, or one still rated "must_treat" under any method,
    doesn't count.
    """
    entries = RiskEntry.objects.filter(
        product=product,
        entry_type__in=[EntryType.THREAT, EntryType.HAZARD],
        scope_hardware_variant__isnull=True,
        scope_software_release__isnull=True,
        scope_software_option__isnull=True,
    ).prefetch_related("treatments__method")

    total = 0
    acceptable = 0
    for entry in entries:
        total += 1
        treatments = list(entry.treatments.all())
        if treatments and all(
            evaluate_residual_rating(t)["acceptance"] in ACCEPTABLE_RESIDUAL_RATINGS
            for t in treatments
        ):
            acceptable += 1
    return acceptable, total


class ApprovedEntityError(Exception):
    """Raised when trying to delete an entity that has already been approved."""


class InvalidStatusTransition(Exception):
    """Raised when a Product status change isn't allowed from its current status."""


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


def approve_product(product: Product, *, actor):
    """Approve a Product and, on first approval, advance its status too.

    is_approved/approved_at/approved_by (delete protection, shared with
    every other product-level entity) and status (this product's own
    lifecycle stage) are separate concepts that happen to move together
    here: approving a still-draft product is what makes it "Approved".
    """
    approve(product, actor=actor)
    if product.status == ProductStatus.DRAFT:
        product.status = ProductStatus.APPROVED
        product.save(update_fields=["status"])


def close_product(product: Product):
    if product.status != ProductStatus.APPROVED:
        raise InvalidStatusTransition("Only an approved product can be closed.")
    product.status = ProductStatus.CLOSED
    product.save(update_fields=["status"])


def archive_product(product: Product):
    if product.status == ProductStatus.DELETED:
        raise InvalidStatusTransition(
            "A deleted product must be restored before it can be archived."
        )
    product.status = ProductStatus.ARCHIVED
    product.save(update_fields=["status"])


def restore_product(product: Product):
    if product.status not in (ProductStatus.ARCHIVED, ProductStatus.DELETED):
        raise InvalidStatusTransition("Only an archived or deleted product can be restored.")
    product.status = ProductStatus.APPROVED if product.is_approved else ProductStatus.DRAFT
    product.save(update_fields=["status"])


def soft_delete_product(product: Product):
    if product.status not in (ProductStatus.DRAFT, ProductStatus.ARCHIVED):
        raise InvalidStatusTransition("Archive an approved or closed product before deleting it.")
    product.status = ProductStatus.DELETED
    product.save(update_fields=["status"])


def _unique_copy(queryset, field: str, base: str) -> str:
    """Find an unused value for ``field`` in ``queryset``, suffixing "copy" / "copy N"."""
    candidate = f"{base} copy"
    n = 2
    while queryset.filter(**{field: candidate}).exists():
        candidate = f"{base} copy {n}"
        n += 1
    return candidate


def clone_hardware_variant(variant: HardwareVariant) -> HardwareVariant:
    """Copy a variant's own fields and target markets. Revisions are not copied."""
    siblings = HardwareVariant.objects.filter(product=variant.product)
    name = _unique_copy(siblings, "name", variant.name)
    slug = _unique_copy(siblings, "slug", slugify(name))
    clone = HardwareVariant.objects.create(product=variant.product, name=name, slug=slug)
    clone.target_markets.set(variant.target_markets.all())
    return clone


def clone_hardware_revision(revision: HardwareRevision) -> HardwareRevision:
    """Copy a revision as a new, unreleased revision of the same variant."""
    siblings = HardwareRevision.objects.filter(hardware_variant=revision.hardware_variant)
    label = _unique_copy(siblings, "label", revision.label)
    return HardwareRevision.objects.create(hardware_variant=revision.hardware_variant, label=label)


def clone_software_release(release: SoftwareRelease) -> SoftwareRelease:
    """Copy a release as a new, unreleased version under the same name."""
    siblings = SoftwareRelease.objects.filter(product=release.product, name=release.name)
    version = _unique_copy(siblings, "version", release.version)
    return SoftwareRelease.objects.create(
        product=release.product, name=release.name, version=version
    )


def clone_software_option(option: SoftwareOption) -> SoftwareOption:
    siblings = SoftwareOption.objects.filter(software_release=option.software_release)
    name = _unique_copy(siblings, "name", option.name)
    slug = _unique_copy(siblings, "slug", slugify(name))
    return SoftwareOption.objects.create(
        software_release=option.software_release,
        name=name,
        slug=slug,
        description=option.description,
    )


def _grantee_filter(user):
    group_ids = list(user.groups.values_list("id", flat=True))
    grantee_filter = Q(user=user)
    if group_ids:
        grantee_filter |= Q(group_id__in=group_ids)
    return grantee_filter


def editable_product_families(user, role: str | None = Role.EDITOR):
    """ProductFamily objects where ``user`` holds ``role``, inherited from its organisation.

    ``role=None`` means any role at all -- roles aren't tiered (an
    Editor grant doesn't imply Viewer; each is its own RoleAssignment),
    so "can this user see it, under any role" needs the filter dropped
    entirely, not swapped to Role.VIEWER.
    """
    if not user.is_authenticated:
        return ProductFamily.objects.none()
    if user.is_superuser:
        return ProductFamily.objects.all()

    role_filter = _grantee_filter(user)
    if role is not None:
        role_filter &= Q(role=role)
    org_ids = RoleAssignment.objects.filter(role_filter, organisation__isnull=False).values_list(
        "organisation_id", flat=True
    )
    family_ids = RoleAssignment.objects.filter(
        role_filter, product_family__isnull=False
    ).values_list("product_family_id", flat=True)
    return ProductFamily.objects.filter(
        Q(organisation_id__in=org_ids) | Q(id__in=family_ids)
    ).distinct()


def editable_products(user, role: str | None = Role.EDITOR):
    """Product objects where ``user`` holds ``role``, at any scope in its hierarchy.

    ``role=None`` means any role at all (see `editable_product_families`).
    """
    if not user.is_authenticated:
        return Product.objects.none()
    if user.is_superuser:
        return Product.objects.all()

    role_filter = _grantee_filter(user)
    if role is not None:
        role_filter &= Q(role=role)
    product_ids = RoleAssignment.objects.filter(role_filter, product__isnull=False).values_list(
        "product_id", flat=True
    )
    families = editable_product_families(user, role=role)
    return (
        Product.objects.filter(Q(product_family__in=families) | Q(id__in=product_ids))
        .exclude(status=ProductStatus.DELETED)
        .distinct()
    )
