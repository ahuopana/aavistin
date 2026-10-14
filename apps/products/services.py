"""Product-level authoring: permission scoping, approval and delete protection.

Kept separate from models.py and views.py, matching the pattern in
apps.orgs.services / apps.assessments.services: read-side scoping queries
and small write-side rules, not persistence or request handling.
"""

from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from apps.assessments.evaluation import evaluate_configuration
from apps.assessments.progress import questionnaire_progress
from apps.orgs.models import ProductFamily, Role, RoleAssignment
from apps.packages.models import RequirementPackage
from apps.risk.mitigation import mitigation_controls, treatment_counts
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


COMPLIANCE_HINT = (
    "Requirements in scope whose package has no action-required finding, "
    "across the product's configurations"
)


def compliance_breakdown(product) -> list[dict]:
    """Per configuration, the in-scope packages of its current evaluation
    (live, not frozen to an approved snapshot) with their requirements and
    the action-required findings that block them. ``compliance_ratio`` is
    computed from this, so the ratio and its breakdown always agree.

    Each item: ``{configuration, assessment (latest, or None), packages:
    [{source, version, title, requirements: [{id, label, ref}], blocking:
    [finding]}], out_of_scope: [package title]}``.
    """
    configurations = Configuration.objects.filter(software_release__product=product).order_by("pk")
    breakdown = []
    for configuration in configurations:
        evaluation = evaluate_configuration(configuration)
        packages = {
            p.pk: p
            for p in RequirementPackage.objects.filter(
                pk__in=[r.get("package_id") for r in evaluation["results"]]
            )
        }
        items = []
        out_of_scope = []
        for result in evaluation["results"]:
            content = getattr(packages.get(result.get("package_id")), "content", {})
            if not result["in_scope"]:
                out_of_scope.append(content.get("title") or result["source"])
                continue
            by_id = {r["id"]: r for r in content.get("requirements", [])}
            items.append(
                {
                    "source": result["source"],
                    "version": result["version"],
                    "title": content.get("title") or result["source"],
                    "requirements": [
                        {
                            "id": requirement_id,
                            "label": by_id.get(requirement_id, {}).get("label") or requirement_id,
                            "ref": by_id.get(requirement_id, {}).get("ref", ""),
                        }
                        for requirement_id in result["requirements"]
                    ],
                    "blocking": [
                        {**f, "anchor": f"finding-{f['source']}-{f['id']}"}
                        for f in evaluation["findings"]
                        if f["level"] == "action_required"
                        and (f["source"], f["version"]) == (result["source"], result["version"])
                    ],
                }
            )
        breakdown.append(
            {
                "configuration": configuration,
                "assessment": configuration.assessments.first(),
                "packages": items,
                "out_of_scope": out_of_scope,
            }
        )
    return breakdown


class Ratio(tuple):
    """``(ok, total)`` plus ``empty``: what to show instead of the ratio
    when ``total`` is 0 (templates read ``ratio.0``, ``ratio.1`` and
    ``ratio.empty``)."""

    empty = "no data yet"

    def __new__(cls, ok, total, empty=None):
        ratio = super().__new__(cls, (ok, total))
        if empty:
            ratio.empty = empty
        return ratio


NOT_IN_SCOPE = "Not in scope"
NOTHING_IN_FORCE = "None in force yet"


def _empty_compliance_label(breakdown) -> str | None:
    """Why a product has no requirements to count: ``NOT_IN_SCOPE`` when its
    configurations were evaluated against active packages and none is in
    scope; ``NOTHING_IN_FORCE`` when a package is in scope but none of its
    requirements is in force yet; None (no data yet) otherwise."""
    if any(item["packages"] for item in breakdown):
        return NOTHING_IN_FORCE
    if any(item["out_of_scope"] for item in breakdown):
        return NOT_IN_SCOPE
    return None


def compliance_ratio(product, breakdown=None) -> Ratio:
    """(fulfilled, total) in-scope requirements across the product's
    configurations' current evaluation (see ``compliance_breakdown``). A
    requirement counts as fulfilled unless its package has an unresolved
    action-required finding in that evaluation -- findings aren't tracked
    per requirement, only per package, so this is a package-level proxy,
    not a true per-requirement pass/fail. A requirement in force for several
    configurations counts once, and as unfulfilled if any of them blocks it.
    """
    total: set[tuple[str, str, str]] = set()
    bad: set[tuple[str, str, str]] = set()
    if breakdown is None:
        breakdown = compliance_breakdown(product)
    for item in breakdown:
        for package in item["packages"]:
            for requirement in package["requirements"]:
                key = (package["source"], package["version"], requirement["id"])
                total.add(key)
                if package["blocking"]:
                    bad.add(key)
    return Ratio(len(total - bad), len(total), _empty_compliance_label(breakdown))


def questions_ratio(product) -> tuple[int, int]:
    """(done, total) active questions summed over the product's
    configurations, per apps.assessments.progress. A product-level answer
    shared by several configurations counts once per configuration,
    since each configuration's questionnaire has to be complete on its
    own.
    """
    done = total = 0
    configurations = Configuration.objects.filter(software_release__product=product)
    for configuration in configurations:
        progress = questionnaire_progress(configuration)
        done += progress["done"]
        total += progress["total"]
    return done, total


def risk_ratio(product) -> tuple[int, int]:
    """(acceptable, total) baseline threat/hazard entries, where
    "acceptable" means every method treatment on the entry has a
    residual acceptance of "accept" or "justify" -- an entry with no
    treatment yet, or one still rated "must_treat" under any method,
    doesn't count. A mitigation also only counts once its controls are
    in place (apps.risk.mitigation): a planned control is not yet a
    reduced risk.
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
        controls = mitigation_controls(entry) if treatments else []
        if treatments and all(
            evaluate_residual_rating(t)["acceptance"] in ACCEPTABLE_RESIDUAL_RATINGS
            and treatment_counts(t, controls)
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
        return instance.product
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
    clone = SoftwareRelease.objects.create(
        product=release.product, name=release.name, version=version
    )
    clone.target_markets.set(release.target_markets.all())
    return clone


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
