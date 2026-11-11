from django.contrib import admin
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.forms import ALL_FIELDS, ModelForm
from django.http import HttpRequest
from django.utils.translation import gettext as _

from polyfile.apps.storage.models import (
    FsNode,
    FsNodeArchiveItem,
    FsNodeArchiveJob,
    FsNodeDeletionJob,
    FsStorage,
    PendingObjectDeletion,
    TempUpload,
)
from polyfile.apps.storage.utils import get_md5_sum, get_mime_type


@admin.register(FsStorage)
class StorageAdmin(admin.ModelAdmin):
    list_display = ("name", "backend")
    change_form_template = "admin/storage/fsstorage_change_form.html"


class FsNodeAdminForm(ModelForm):
    class Meta:
        model = FsNode
        fields = ALL_FIELDS

    def save(self, commit: bool = True) -> models.Model:
        if self.instance.is_file and (file := self.files.get("file")) is not None:
            assert isinstance(file, InMemoryUploadedFile)
            self.instance.size = file.size
            self.instance.md5 = get_md5_sum(file)
            self.instance.mime_type = get_mime_type(file)
        return super().save(commit=commit)


@admin.register(FsNode)
class FsNodeAdmin(admin.ModelAdmin):
    ordering = ("name",)
    list_display = ("id", "type", "name", "display_file_name", "display_is_deleted")
    list_filter = ("storage", "type", "deleted_at")
    raw_id_fields = ("storage", "owner", "parent")
    readonly_fields = ("size", "mime_type", "md5", "created_at", "modified_at", "deletion_job")
    form = FsNodeAdminForm

    @admin.display(description=_("File name"))
    def display_file_name(self, obj: FsNode | None) -> str:
        if obj and obj.file:
            return obj.file.name
        return ""

    @admin.display(description=_("Deleted"), boolean=True)
    def display_is_deleted(self, obj: FsNode | None) -> bool:
        return obj is not None and obj.deleted_at is not None

    def get_readonly_fields(self, request: HttpRequest, obj: FsNode | None = None) -> tuple:
        if obj is None:
            return self.readonly_fields
        else:
            return ("id", "owner", "storage", "type") + self.readonly_fields


@admin.register(TempUpload)
class TempUploadAdmin(admin.ModelAdmin):
    list_display = ("token", "fs_node_id", "status", "created_at", "completed_on")
    list_filter = ("status",)
    raw_id_fields = ("fs_node",)


@admin.register(FsNodeDeletionJob)
class FsNodeDeletionJob(admin.ModelAdmin):
    list_display = ("id", "root_path", "status", "total_nodes",)
    list_filter = ("status",)


@admin.register(PendingObjectDeletion)
class PendingObjectDeletionAdmin(admin.ModelAdmin):
    list_display = ("storage_id", "object_key", "node_uuid", "created_at", "attempts")
    list_filter = ("storage_id",)
    search_fields = ("object_key", "node_uuid")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(FsNodeArchiveJob)
class FsNodeArchiveJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "root_node_name",
        "status",
        "total_files",
        "total_bytes",
        "created_at",
        "expires_at",
    )
    list_filter = ("status",)
    search_fields = ("root_node_name", "root_node_uuid", "fingerprint")
    raw_id_fields = ("requested_by",)
    readonly_fields = (
        "id",
        "created_at",
        "started_at",
        "finished_at",
        "archive_size",
        "archive_md5",
    )
    date_hierarchy = "created_at"


@admin.register(FsNodeArchiveItem)
class FsNodeArchiveItemAdmin(admin.ModelAdmin):
    list_display = ("job", "entry_type", "zip_path", "size", "position")
    list_filter = ("entry_type",)
    search_fields = ("zip_path", "object_key")
    raw_id_fields = ("job", "node")
    ordering = ("job", "position")
    list_select_related = ("job", "node")
