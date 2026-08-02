from collections.abc import Sequence
from typing import ClassVar

from django import forms
from django.contrib import admin
from django.core import exceptions
from django.core.files.storage import InvalidStorageError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from django.forms import ALL_FIELDS, ModelForm
from django.forms.widgets import Widget
from django.http import HttpRequest
from django.utils.translation import gettext as _

from polyfile.storage.handler import fs_storages, registered_backends
from polyfile.storage.models import FsNode, Storage, TempUpload
from polyfile.storage.utils import get_md5_sum, get_mime_type


class OptionsWidget(forms.MultiWidget):
    widgets: dict
    widgets_names: list[str]

    template_name = 'forms/widgets/labeled-multiwidget.html'

    def __init__(self, widgets: dict[str, Widget], labels: Sequence[str], attrs=None):
        self.labels = labels
        super().__init__(widgets, attrs)

    def decompress(self, value: dict):
        # value: dict = json.loads(value)
        return tuple(value.get(key.lstrip('_')) for key in self.widgets_names)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)

        # Zip the generated subwidgets and custom labels together to inject them
        for subwidget, label in zip(context['widget']['subwidgets'], self.labels):
            subwidget['custom_label'] = label  # Assign new key into the subwidget context

        return context


class OptionsField(forms.MultiValueField):
    def __init__(self, fields: dict[str, forms.Field], **kwargs):
        self.subfields = fields

        super().__init__(
            fields=list(self.subfields.values()),
            widget=OptionsWidget(
                widgets={key: field.widget for key, field in self.subfields.items()},
                labels=tuple(field.label or key.capitalize() for key, field in self.subfields.items()),
            ),
            **kwargs,
        )

    def compress(self, data_list: list):
        """
        Merges sub-widget clean inputs into a single object for the JSONField.
        :param data_list: Validated data from each sub-field.
        """
        if data_list:
            return dict(
                zip(
                    self.subfields.keys(),
                    data_list,
                )
            )
        return {}


class StorageAdminForm(ModelForm):
    class Meta:
        model = Storage
        fields = ALL_FIELDS
        help_texts: ClassVar = {
            'backend': 'Options depends on this field',
        }

    def __init__(self, data=None, *args, **kwargs):
        instance = kwargs.get('instance')
        super().__init__(data, *args, **kwargs)
        storage_backend = None
        try:
            if data is not None and 'backend' in data:
                storage_backend = registered_backends[data['backend']]
            elif instance is not None:
                storage_backend = fs_storages[instance.pk]
        except InvalidStorageError:
            pass

        if storage_backend is not None:
            self.fields['options'] = OptionsField(
                fields=storage_backend.get_option_fields(),
            )

    def clean(self):
        """Validate fields."""
        if not self.errors:
            try:
                fs_storages.create_storage({
                    "BACKEND": self.cleaned_data.get("backend", ""),
                    "OPTIONS": self.cleaned_data.get("options", {})
                })
            except InvalidStorageError as e:
                raise exceptions.ValidationError({"backend": str(e)})

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
    list_display = ("id", "type", "name", "storage_id", "display_file_name", "created_at")
    list_filter = ("storage", "type")
    raw_id_fields = ("storage", "owner", "parent")
    readonly_fields = ("size", "mime_type", "md5", "created_at", "modified_at")
    form = FsNodeAdminForm

    @admin.display(description=_("File name"))
    def display_file_name(self, obj: FsNode | None) -> str | None:
        return obj and obj.file and obj.file.name

    def get_readonly_fields(self, request: HttpRequest, obj: FsNode | None = None) -> tuple:
        if obj is None:
            return self.readonly_fields
        else:
            return ("id", "owner", "storage", "type") + self.readonly_fields


@admin.register(TempUpload)
class TempUploadAdmin(admin.ModelAdmin):
    list_display = ('token', 'fs_node_id', 'status', 'created_at', 'completed_on')
    list_filter = ('status',)
    raw_id_fields = ('fs_node',)
