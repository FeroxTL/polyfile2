from pathlib import PurePosixPath

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import fields
from django.forms.models import ModelForm

from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.file_system_backend.models import LocalDiskStorage
from polyfile.contrib.backends.utils import get_storage_path


class LocalDiskStorageForm(ModelForm):
    backend_path: str = get_storage_path(FileSystemBackend)
    location = fields.CharField(
        required=True,
        help_text='Path to the directory, can be relative to working directory or absolute.',
    )
    upload_to = fields.CharField(
        required=False,
        help_text='Relative path inside location directory. Date formatters can be used',
    )

    class Meta:
        model = LocalDiskStorage
        fields = '__all__'
        exclude = ('backend', 'options')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].initial = self.instance.options.get('location', '')
        self.fields['upload_to'].initial = self.instance.options.get('upload_to', '%Y/%m/%d/')

    def clean_upload_to(self) -> str:
        value = PurePosixPath(self.cleaned_data.get('upload_to', ''))
        if value.is_absolute():
            raise ValidationError('The upload_to path cannot be absolute.')
        return str(value)


    def save(self, commit: bool = True) -> LocalDiskStorage:
        self.instance.backend = self.backend_path
        self.instance.options.update({
            'location': self.cleaned_data['location'],
            'upload_to': self.cleaned_data['upload_to'],
        })
        return super().save(commit=commit)


@admin.register(LocalDiskStorage)
class LocalDiskStorageAdmin(admin.ModelAdmin):
    form = LocalDiskStorageForm
