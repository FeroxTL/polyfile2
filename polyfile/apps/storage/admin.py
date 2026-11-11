from django.contrib import admin
from django.db import models
from django.http import HttpRequest
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from polyfile.apps.storage.archive_backend import get_archive_backend
from polyfile.apps.storage.archive_delivery import archive_download_filename
from polyfile.apps.storage.models import (
    FsNode,
    FsNodeArchiveItem,
    FsNodeArchiveJob,
    FsNodeDeletionJob,
    FsStorage,
    PendingObjectDeletion,
)


@admin.register(FsStorage)
class StorageAdmin(admin.ModelAdmin):
    list_display = ("name", "backend")
    change_form_template = "admin/storage/fsstorage_change_form.html"


@admin.register(FsNode)
class FsNodeAdmin(admin.ModelAdmin):
    ordering = ("name",)
    list_display = ("id", "type", "name", "file_display", "display_is_deleted")
    list_filter = ("storage", "type", "deleted_at")
    raw_id_fields = ("storage", "owner", "parent")
    readonly_fields = (
        "size",
        "mime_type",
        "md5",
        "created_at",
        "modified_at",
        "deletion_job",
    )
    exclude = ("object_key",)

    @admin.display(description=_("File"))
    def file_display(self, obj: FsNode | None) -> str:
        if obj is None or not obj.file:
            return "-"
        return format_html(
            '<strong>{}</strong>: <code>{}</code> (<a href="{}">download</a>)',
            obj.storage,
            obj.object_key,
            obj.file.download_url(),
        )

    @admin.display(description=_("Deleted"), boolean=True)
    def display_is_deleted(self, obj: FsNode | None) -> bool:
        return obj is not None and obj.deleted_at is not None

    def get_readonly_fields(self, request: HttpRequest, obj: FsNode | None = None) -> tuple:
        if obj is None:
            return self.readonly_fields
        return ("id", "owner", "storage", "type", "file_display") + self.readonly_fields

    def get_fields(self, request: HttpRequest, obj: FsNode | None = None) -> tuple:
        fields = list(super().get_fields(request, obj))
        if "object_key" in fields:
            fields.remove("object_key")
        return tuple(fields)


class TempUploadAdmin(admin.ModelAdmin):
    list_display = ("token", "fs_node_id", "status", "created_at", "completed_on")
    list_filter = ("status",)
    raw_id_fields = ("fs_node",)


@admin.register(FsNodeDeletionJob)
class FsNodeDeletionJobAdmin(admin.ModelAdmin):
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
    ordering = ("-created_at",)
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
        "root_node_link",
        "created_at",
        "started_at",
        "finished_at",
        "archive_size",
        "archive_md5",
        "file_display",
    )
    date_hierarchy = "created_at"

    @admin.display(description=_("Root node"))
    def root_node_link(self, obj: FsNodeArchiveJob | None) -> str:
        if obj is None:
            return "-"
        if FsNode.objects.filter(pk=obj.root_node_uuid).exists():
            url = reverse("admin:storage_fsnode_change", args=[obj.root_node_uuid])
            return format_html('<a href="{}">{}</a>', url, obj.root_node_uuid)
        return str(obj.root_node_uuid)

    @admin.display(description=_("Archive file"))
    def file_display(self, obj: FsNodeArchiveJob | None) -> str:
        if obj is None:
            return "-"
        if obj.status != FsNodeArchiveJob.Status.READY or not obj.archive_key:
            return "-"
        url = reverse("archive_job_file", kwargs={"job_id": obj.pk})
        filename = archive_download_filename(obj)
        return format_html('<a href="{}">{}</a>', url, filename)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: FsNodeArchiveJob | None = None) -> bool:
        return False

    def delete_model(self, request: HttpRequest, obj: FsNodeArchiveJob) -> None:
        self._delete_archive_file(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request: HttpRequest, queryset: models.QuerySet[FsNodeArchiveJob]) -> None:
        for job in queryset.iterator():
            self._delete_archive_file(job)
        super().delete_queryset(request, queryset)

    @staticmethod
    def _delete_archive_file(job: FsNodeArchiveJob) -> None:
        if job.archive_key:
            get_archive_backend().delete(job.archive_key)


@admin.register(FsNodeArchiveItem)
class FsNodeArchiveItemAdmin(admin.ModelAdmin):
    list_display = ("job", "entry_type", "zip_path", "file_display", "size", "position")
    list_filter = ("entry_type",)
    search_fields = ("zip_path", "object_key")
    raw_id_fields = ("job", "node")
    readonly_fields = (
        "job",
        "node",
        "entry_type",
        "zip_path",
        "file_display",
        "size",
        "md5",
        "modified_at",
        "position",
    )
    ordering = ("job", "position")
    list_select_related = ("job", "node")
    exclude = ("object_key", "storage_id")

    @admin.display(description=_("File"))
    def file_display(self, obj: FsNodeArchiveItem | None) -> str:
        if obj is None or not obj.file:
            return "-"
        return format_html(
            '<strong>storage {}</strong>: <code>{}</code>',
            obj.storage_id,
            obj.object_key,
        )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: FsNodeArchiveItem | None = None) -> bool:
        return False

    def get_fields(self, request: HttpRequest, obj: FsNodeArchiveItem | None = None) -> tuple:
        fields = list(super().get_fields(request, obj))
        for hidden in ("object_key", "storage_id"):
            if hidden in fields:
                fields.remove(hidden)
        return tuple(fields)
