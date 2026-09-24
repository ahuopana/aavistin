from django.contrib import admin

from .models import (
    Configuration,
    HardwareRevision,
    HardwareVariant,
    Product,
    SoftwareOption,
    SoftwareRelease,
    TargetMarket,
)


@admin.register(TargetMarket)
class TargetMarketAdmin(admin.ModelAdmin):
    list_display = ("code", "name")


class HardwareVariantInline(admin.TabularInline):
    model = HardwareVariant
    extra = 0


class SoftwareReleaseInline(admin.TabularInline):
    model = SoftwareRelease
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "product_family", "status")
    list_filter = ("product_family", "status")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [HardwareVariantInline, SoftwareReleaseInline]


class HardwareRevisionInline(admin.TabularInline):
    model = HardwareRevision
    extra = 0


@admin.register(HardwareVariant)
class HardwareVariantAdmin(admin.ModelAdmin):
    list_display = ("name", "product")
    list_filter = ("product",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [HardwareRevisionInline]
    filter_horizontal = ("target_markets",)


@admin.register(HardwareRevision)
class HardwareRevisionAdmin(admin.ModelAdmin):
    list_display = ("__str__", "released_at")
    list_filter = ("hardware_variant__product",)


class SoftwareOptionInline(admin.TabularInline):
    model = SoftwareOption
    extra = 0


@admin.register(SoftwareRelease)
class SoftwareReleaseAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "product", "released_at")
    list_filter = ("product",)
    inlines = [SoftwareOptionInline]


@admin.register(SoftwareOption)
class SoftwareOptionAdmin(admin.ModelAdmin):
    list_display = ("name", "software_release")
    list_filter = ("software_release__product",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Configuration)
class ConfigurationAdmin(admin.ModelAdmin):
    list_display = ("name", "hardware_revision", "software_release", "created_at")
    filter_horizontal = ("software_options",)
