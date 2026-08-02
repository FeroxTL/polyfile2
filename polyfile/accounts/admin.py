from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext as _

from polyfile.accounts.models import User


@admin.register(User)
class StorageAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets[:2] + (
            (_('Storage'), {'fields': ('storage',)}),
    ) + UserAdmin.fieldsets[2:]
    raw_id_fields = UserAdmin.raw_id_fields + ('storage',)
    list_display = ('username', 'email', 'full_name', 'storage', 'is_staff')
