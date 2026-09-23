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
    SoftwareOption,
    SoftwareRelease,
    TargetMarket,
)
from .services import (
    ApprovedEntityError,
    approve,
    compliance_ratio,
    delete_entity,
    product_of,
    risk_ratio,
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
    if isinstance(instance, Product):
        return redirect("orgs:detail", slug=instance.product_family.organisation.slug)
    return redirect("products:product_detail", pk=product_of(instance).pk)


@login_required
def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    configurations = Configuration.objects.filter(
        hardware_revision__hardware_variant__product=product
    ).prefetch_related("software_options")
    hardware_revisions = HardwareRevision.objects.filter(hardware_variant__product=product)
    software_releases = product.sw_releases.all()
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
            "can_edit": has_role(request.user, Role.EDITOR, product=product),
            "can_approve": has_role(request.user, Role.APPROVER, product=product),
        },
    )


@login_required
def product_create(request, family_id):
    family = get_object_or_404(ProductFamily, pk=family_id)
    if not has_role(request.user, Role.EDITOR, product_family=family):
        django_messages.error(request, "You need the editor role to add products.")
        return redirect("orgs:detail", slug=family.organisation.slug)

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
            return redirect("orgs:detail", slug=family.organisation.slug)
        product.save()
        django_messages.success(request, "Product created.")
        return redirect("products:product_detail", pk=product.pk)

    return redirect("orgs:detail", slug=family.organisation.slug)


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
    try:
        delete_entity(instance)
        django_messages.success(request, "Deleted.")
    except ApprovedEntityError as exc:
        django_messages.error(request, str(exc))
    return owner_redirect
