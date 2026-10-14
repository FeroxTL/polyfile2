from django.contrib import admin

from polyfile.apps.share.models import SharedNode, ShareDownload


@admin.register(SharedNode)
class SharedNodeAdmin(admin.ModelAdmin):
    list_display = ("token", "root_fs_node", "is_active", "expires_at", "revoked_at")
    raw_id_fields = ("root_fs_node", "owner")
    search_fields = ("=token", "=root_fs_node__id")
    readonly_fields = ("token",)


@admin.register(ShareDownload)
class ShareDownloadAdmin(admin.ModelAdmin):
    raw_id_fields = ("share",)
