from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Identity", {"fields": ("auth_source",)}),)
    list_display = ("username", "email", "auth_source", "is_staff", "is_active")
    list_filter = DjangoUserAdmin.list_filter + ("auth_source",)
