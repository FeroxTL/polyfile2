from django.contrib.staticfiles.storage import StaticFilesStorage
from django.db import models
from django.urls import reverse

from polyfile.storage.backends import BaseStorageBackend
from polyfile.storage.tokens import default_token_generator


class LocalDiskBackend(StaticFilesStorage, BaseStorageBackend):
    """Stores files in a directory on the local device."""
    def download_url(self, instance: models.Model):
        return reverse('download_file', kwargs={
            'pk': instance.pk,
            'token': default_token_generator.make_token(instance),
        })


__all__ = ("LocalDiskBackend",)
