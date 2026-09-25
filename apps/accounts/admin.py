from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import PasswordHistory, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "username", "first_name", "last_name", "role", "is_active")
    list_filter = ("role", "is_active", "is_staff", "is_deleted")
    search_fields = ("email", "username", "first_name", "last_name")
    ordering = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "phone", "avatar")}),
        ("Role & Lab", {"fields": ("role", "laboratory")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Security", {"fields": ("requires_2fa", "force_password_change", "last_password_change")}),
        ("Status", {"fields": ("is_deleted", "date_joined", "last_login")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2", "role"),
        }),
    )


@admin.register(PasswordHistory)
class PasswordHistoryAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    list_filter = ("created_at",)
    readonly_fields = ("user", "password_hash", "created_at")