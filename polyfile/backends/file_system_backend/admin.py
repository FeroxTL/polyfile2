from django.contrib import admin
from django.forms import fields
from django.forms.models import ModelForm

from polyfile.backends.file_system_backend.backend import FileSystemBackend
from polyfile.backends.file_system_backend.models import LocalDiskStorage
from polyfile.backends.utils import get_storage_path


class LocalDiskStorageForm(ModelForm):
    backend_path: str = get_storage_path(FileSystemBackend)
    location = fields.CharField(required=True)

    class Meta:
        model = LocalDiskStorage
        fields = '__all__'
        exclude = ('backend', 'options')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['location'].initial = self.instance.options.get('location', '')

    def save(self, commit: bool = True) -> LocalDiskStorage:
        self.instance.backend = self.backend_path
        self.instance.options.update({
            'location': self.cleaned_data['location'],
        })
        return super().save(commit=commit)


@admin.register(LocalDiskStorage)
class LocalDiskStorageAdmin(admin.ModelAdmin):
    form = LocalDiskStorageForm
