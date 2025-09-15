from django.contrib import admin
from django.core import exceptions
from django.core.files.storage import InvalidStorageError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.forms import ModelForm, ALL_FIELDS
from django.http import HttpRequest
from django.utils.translation import gettext as _

from polyfile.storage.handler import fs_storages
from polyfile.storage.models import Storage, FsNode, TempUpload
from polyfile.storage.utils import get_md5_sum, get_mime_type


class StorageAdminForm(ModelForm):
    class Meta:
        model = Storage
        fields = ALL_FIELDS

    def clean(self):
        """Validate fields."""
        backend = self.cleaned_data.get("backend", "")
        try:
            fs_storages.create_storage({
                "BACKEND": backend,
                "OPTIONS": self.cleaned_data.get("options", {})
            })
        except InvalidStorageError as e:
            raise exceptions.ValidationError({"backend": str(e)})
        except Exception as e:
            raise exceptions.ValidationError({"options": str(e)})

        return super().clean()


@admin.register(Storage)
class StorageAdmin(admin.ModelAdmin):
    list_display = ("name", "backend")
    form = StorageAdminForm


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
    list_display = ("id", "type", "name", "storage_id", "display_file_name")
    list_filter = ("storage", "type")
    raw_id_fields = ("storage", "owner", "parent")
    readonly_fields = ("size", "mime_type", "md5")
    form = FsNodeAdminForm

    @admin.display(description=_("File name"))
    def display_file_name(self, obj: FsNode | None) -> str | None:
        return obj and obj.file and obj.file.name

    def get_readonly_fields(self, request: HttpRequest, obj: FsNode | None = None) -> tuple:
        if obj is None:
            return self.readonly_fields
        else:
            return ("owner", "storage", "type") + self.readonly_fields


@admin.register(TempUpload)
class TempUploadAdmin(admin.ModelAdmin):
    list_display = ('token', 'fs_node_id', 'status', 'created_at', 'completed_on')
    list_filter = ('status',)
    raw_id_fields = ('fs_node',)
