from django.contrib import messages as django_messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.orgs.models import ProductFamily, Role
from apps.orgs.services import has_role

from .models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    ProductStatus,
    SoftwareOption,
    SoftwareRelease,
    TargetMarket,
)
from .services import (
    ApprovedEntityError,
    InvalidStatusTransition,
    approve,
    approve_product,
    archive_product,
    clone_hardware_revision,
    clone_hardware_variant,
    clone_software_option,
    clone_software_release,
    close_product,
    compliance_ratio,
    delete_entity,
    product_of,
    restore_product,
    risk_ratio,
    soft_delete_product,
)

ENTITY_MODELS = {
    "product": Product,
    "hardware-variant": HardwareVariant,
    "hardware-revision": HardwareRevision,
    "software-release": SoftwareRelease,
    "software-option": SoftwareOption,
    "configuration": Configuration,
}


def _flash_errors(request, exc: ValidationError):
    if hasattr(exc, "message_dict"):
        for messages in exc.message_dict.values():
            for message in messages:
                django_messages.error(request, message)
    else:
        for message in exc.messages:
            django_messages.error(request, message)


def _redirect_to_owner(instance):
    return redirect("products:product_detail", pk=product_of(instance).pk)


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    configurations = Configuration.objects.filter(
        hardware_revision__hardware_variant__product=product
    ).prefetch_related("software_options")
    hardware_revisions = HardwareRevision.objects.filter(hardware_variant__product=product)
    software_releases = product.sw_releases.all()
    can_edit = has_role(request.user, Role.EDITOR, product=product)
    can_approve = has_role(request.user, Role.APPROVER, product=product)
    return render(
        request,
        "products/product_detail.html",
        {
            "product": product,
            "target_markets": TargetMarket.objects.all(),
            "configurations": configurations,
            "hardware_revisions": hardware_revisions,
            "software_releases": software_releases,
            "compliance": compliance_ratio(product),
            "risk": risk_ratio(product),
            "can_edit": can_edit,
            "can_approve": can_approve,
            "can_close": can_approve and product.status == ProductStatus.APPROVED,
            "can_archive": can_edit
            and product.status
            in (ProductStatus.DRAFT, ProductStatus.APPROVED, ProductStatus.CLOSED),
            "can_restore": can_edit
            and product.status in (ProductStatus.ARCHIVED, ProductStatus.DELETED),
            "can_soft_delete": can_edit
            and product.status in (ProductStatus.DRAFT, ProductStatus.ARCHIVED),
        },
    )


@login_required
def product_create(request, family_id):
    family = get_object_or_404(ProductFamily, pk=family_id)
    if not has_role(request.user, Role.EDITOR, product_family=family):
        django_messages.error(request, "You need the editor role to add products.")
        return redirect("orgs:portfolio")

    if request.method == "POST":
        product = Product(
            product_family=family,
            name=request.POST.get("name", ""),
            slug=request.POST.get("slug", ""),
            description=request.POST.get("description", ""),
        )
        try:
            product.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("orgs:portfolio")
        product.save()
        django_messages.success(request, "Product created.")
        return redirect("products:product_detail", pk=product.pk)

    return redirect("orgs:portfolio")


@login_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit this product.")
        return redirect("products:product_detail", pk=pk)

    if request.method == "POST":
        product.name = request.POST.get("name", "")
        product.slug = request.POST.get("slug", "")
        product.description = request.POST.get("description", "")
        try:
            product.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=pk)
        product.save()
        django_messages.success(request, "Product updated.")
    return redirect("products:product_detail", pk=pk)


@login_required
def hardware_variant_create(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add hardware variants.")
        return redirect("products:product_detail", pk=product_id)

    if request.method == "POST":
        variant = HardwareVariant(
            product=product,
            name=request.POST.get("name", ""),
            slug=request.POST.get("slug", ""),
        )
        try:
            variant.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product_id)
        variant.save()
        variant.target_markets.set(request.POST.getlist("target_markets"))
        django_messages.success(request, "Hardware variant created.")
    return redirect("products:product_detail", pk=product_id)


@login_required
def hardware_variant_edit(request, pk):
    variant = get_object_or_404(HardwareVariant, pk=pk)
    product = variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit hardware variants.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        variant.name = request.POST.get("name", "")
        variant.slug = request.POST.get("slug", "")
        try:
            variant.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        variant.save()
        variant.target_markets.set(request.POST.getlist("target_markets"))
        django_messages.success(request, "Hardware variant updated.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
def hardware_revision_create(request, variant_id):
    variant = get_object_or_404(HardwareVariant, pk=variant_id)
    product = variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add hardware revisions.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        revision = HardwareRevision(
            hardware_variant=variant,
            label=request.POST.get("label", ""),
            released_at=request.POST.get("released_at") or None,
        )
        try:
            revision.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        revision.save()
        django_messages.success(request, "Hardware revision created.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
def hardware_revision_edit(request, pk):
    revision = get_object_or_404(HardwareRevision, pk=pk)
    product = revision.hardware_variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit hardware revisions.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        revision.label = request.POST.get("label", "")
        revision.released_at = request.POST.get("released_at") or None
        try:
            revision.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        revision.save()
        django_messages.success(request, "Hardware revision updated.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
def software_release_create(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add software releases.")
        return redirect("products:product_detail", pk=product_id)

    if request.method == "POST":
        release = SoftwareRelease(
            product=product,
            name=request.POST.get("name", ""),
            version=request.POST.get("version", ""),
            released_at=request.POST.get("released_at") or None,
        )
        try:
            release.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product_id)
        release.save()
        django_messages.success(request, "Software release created.")
    return redirect("products:product_detail", pk=product_id)


@login_required
def software_release_edit(request, pk):
    release = get_object_or_404(SoftwareRelease, pk=pk)
    product = release.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit software releases.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        release.name = request.POST.get("name", "")
        release.version = request.POST.get("version", "")
        release.released_at = request.POST.get("released_at") or None
        try:
            release.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        release.save()
        django_messages.success(request, "Software release updated.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
def software_option_create(request, release_id):
    release = get_object_or_404(SoftwareRelease, pk=release_id)
    product = release.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add software options.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        option = SoftwareOption(
            software_release=release,
            name=request.POST.get("name", ""),
            slug=request.POST.get("slug", ""),
            description=request.POST.get("description", ""),
        )
        try:
            option.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        option.save()
        django_messages.success(request, "Software option created.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
def software_option_edit(request, pk):
    option = get_object_or_404(SoftwareOption, pk=pk)
    product = option.software_release.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit software options.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        option.name = request.POST.get("name", "")
        option.slug = request.POST.get("slug", "")
        option.description = request.POST.get("description", "")
        try:
            option.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        option.save()
        django_messages.success(request, "Software option updated.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
def configuration_create(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to add configurations.")
        return redirect("products:product_detail", pk=product_id)

    if request.method == "POST":
        configuration = Configuration(
            name=request.POST.get("name", ""),
            hardware_revision_id=request.POST.get("hardware_revision") or None,
            software_release_id=request.POST.get("software_release") or None,
        )
        options = list(
            SoftwareOption.objects.filter(pk__in=request.POST.getlist("software_options"))
        )
        try:
            configuration.full_clean()
            configuration.clean_software_options(options)
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product_id)
        configuration.save()
        configuration.software_options.set(options)
        django_messages.success(request, "Configuration created.")
    return redirect("products:product_detail", pk=product_id)


@login_required
def configuration_edit(request, pk):
    configuration = get_object_or_404(Configuration, pk=pk)
    product = product_of(configuration)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to edit configurations.")
        return redirect("products:product_detail", pk=product.pk)

    if request.method == "POST":
        configuration.name = request.POST.get("name", "")
        configuration.hardware_revision_id = request.POST.get("hardware_revision") or None
        configuration.software_release_id = request.POST.get("software_release") or None
        try:
            configuration.full_clean()
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        options = list(
            SoftwareOption.objects.filter(pk__in=request.POST.getlist("software_options"))
        )
        try:
            configuration.clean_software_options(options)
        except ValidationError as exc:
            _flash_errors(request, exc)
            return redirect("products:product_detail", pk=product.pk)
        configuration.save()
        configuration.software_options.set(options)
        django_messages.success(request, "Configuration updated.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
@require_POST
def entity_approve(request, model_name, pk):
    model = ENTITY_MODELS.get(model_name)
    if model is None:
        django_messages.error(request, "Unknown entity type.")
        return redirect("core:home")
    instance = get_object_or_404(model, pk=pk)
    product = product_of(instance)
    if not has_role(request.user, Role.APPROVER, product=product):
        django_messages.error(request, "You need the approver role to approve this.")
        return _redirect_to_owner(instance)
    if isinstance(instance, Product):
        approve_product(instance, actor=request.user)
    else:
        approve(instance, actor=request.user)
    django_messages.success(request, f"{instance} approved.")
    return _redirect_to_owner(instance)


@login_required
@require_POST
def entity_delete(request, model_name, pk):
    model = ENTITY_MODELS.get(model_name)
    if model is None:
        django_messages.error(request, "Unknown entity type.")
        return redirect("core:home")
    instance = get_object_or_404(model, pk=pk)
    product = product_of(instance)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to delete this.")
        return _redirect_to_owner(instance)

    owner_redirect = _redirect_to_owner(instance)
    if isinstance(instance, Product):
        try:
            soft_delete_product(instance)
            django_messages.success(request, "Product deleted (can be restored later).")
        except InvalidStatusTransition as exc:
            django_messages.error(request, str(exc))
        return owner_redirect
    try:
        delete_entity(instance)
        django_messages.success(request, "Deleted.")
    except ApprovedEntityError as exc:
        django_messages.error(request, str(exc))
    return owner_redirect


@login_required
@require_POST
def product_close(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not has_role(request.user, Role.APPROVER, product=product):
        django_messages.error(request, "You need the approver role to close this product.")
        return redirect("products:product_detail", pk=pk)
    try:
        close_product(product)
        django_messages.success(request, "Product closed.")
    except InvalidStatusTransition as exc:
        django_messages.error(request, str(exc))
    return redirect("products:product_detail", pk=pk)


@login_required
@require_POST
def product_archive(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to archive this product.")
        return redirect("products:product_detail", pk=pk)
    try:
        archive_product(product)
        django_messages.success(request, "Product archived.")
    except InvalidStatusTransition as exc:
        django_messages.error(request, str(exc))
    return redirect("products:product_detail", pk=pk)


@login_required
@require_POST
def product_restore(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to restore this product.")
        return redirect("products:product_detail", pk=pk)
    try:
        restore_product(product)
        django_messages.success(request, "Product restored.")
    except InvalidStatusTransition as exc:
        django_messages.error(request, str(exc))
    return redirect("products:product_detail", pk=pk)


@login_required
@require_POST
def hardware_variant_clone(request, pk):
    variant = get_object_or_404(HardwareVariant, pk=pk)
    product = variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to clone hardware variants.")
        return redirect("products:product_detail", pk=product.pk)
    clone = clone_hardware_variant(variant)
    django_messages.success(request, f"Cloned as {clone.name}.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
@require_POST
def hardware_revision_clone(request, pk):
    revision = get_object_or_404(HardwareRevision, pk=pk)
    product = revision.hardware_variant.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to clone hardware revisions.")
        return redirect("products:product_detail", pk=product.pk)
    clone = clone_hardware_revision(revision)
    django_messages.success(request, f"Cloned as rev {clone.label}.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
@require_POST
def software_release_clone(request, pk):
    release = get_object_or_404(SoftwareRelease, pk=pk)
    product = release.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to clone software releases.")
        return redirect("products:product_detail", pk=product.pk)
    clone = clone_software_release(release)
    django_messages.success(request, f"Cloned as {clone.name} {clone.version}.")
    return redirect("products:product_detail", pk=product.pk)


@login_required
@require_POST
def software_option_clone(request, pk):
    option = get_object_or_404(SoftwareOption, pk=pk)
    product = option.software_release.product
    if not has_role(request.user, Role.EDITOR, product=product):
        django_messages.error(request, "You need the editor role to clone software options.")
        return redirect("products:product_detail", pk=product.pk)
    clone = clone_software_option(option)
    django_messages.success(request, f"Cloned as {clone.name}.")
    return redirect("products:product_detail", pk=product.pk)
