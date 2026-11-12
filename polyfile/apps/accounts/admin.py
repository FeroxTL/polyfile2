from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.timezone import now
from django.utils.translation import gettext as _

from polyfile.apps.accounts.models import ApiKey, User


@admin.register(User)
class StorageAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets[:2] + (
            (_('Storage'), {'fields': ('storage',)}),
    ) + UserAdmin.fieldsets[2:]
    raw_id_fields = UserAdmin.raw_id_fields + ('storage',)
    list_display = ('username', 'email', 'full_name', 'storage', 'is_staff')


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "user",
        "prefix",
        "is_active",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    )
    list_filter = ("revoked_at", "expires_at")
    search_fields = ("name", "=prefix", "user__username")
    raw_id_fields = ("user",)
    readonly_fields = (
        "id",
        "prefix",
        "key_hash",
        "created_at",
        "last_used_at",
    )
    date_hierarchy = "created_at"
    actions = ("revoke",)

    @admin.action(description="Revoke selected API keys")
    def revoke(self, request, queryset) -> None:
        """Mark selected keys as revoked."""
        updated = queryset.filter(revoked_at__isnull=True).update(
            revoked_at=now(),
        )
        self.message_user(request, f"Revoked {updated} API key(s).")
