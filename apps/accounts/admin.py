from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User, UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    exclude = ("avatar", "avatar_updated_at")


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (("Identity", {"fields": ("auth_source",)}),)
    inlines = [UserProfileInline]
    list_display = ("username", "email", "auth_source", "is_staff", "is_active")
    list_filter = DjangoUserAdmin.list_filter + ("auth_source",)
