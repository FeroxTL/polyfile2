from django.db import models
from django.db.models import Model, QuerySet

from polyfile.backends.file_system_backend.backend import FileSystemBackend
from polyfile.backends.utils import get_storage_path
from polyfile.storage.models import Storage


class LocalDiskStorageManager(models.Manager):
    def get_queryset(self) -> QuerySet[Model, Model]:
        # TODO: remove const
        return super().get_queryset().filter(backend=get_storage_path(FileSystemBackend))


class LocalDiskStorage(Storage):
    class Meta:
        proxy = True
        verbose_name = 'Local disk storage'
        verbose_name_plural = 'Local disk storages'

    objects = LocalDiskStorageManager()
