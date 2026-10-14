from django.contrib import admin
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.forms import ALL_FIELDS, ModelForm
from django.http import HttpRequest
from django.utils.translation import gettext as _

from polyfile.apps.storage.models import FsNode, FsStorage, TempUpload
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
    list_display = ("id", "type", "name", "storage_id", "display_file_name", "created_at")
    list_filter = ("storage", "type")
    raw_id_fields = ("storage", "owner", "parent")
    readonly_fields = ("size", "mime_type", "md5", "created_at", "modified_at")
    form = FsNodeAdminForm

    @admin.display(description=_("File name"))
    def display_file_name(self, obj: FsNode | None) -> str:
        if obj and obj.file:
            return obj.file.name
        return ""

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
