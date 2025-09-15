from django.core.files.storage import Storage
from django.db import models


class BaseStorageBackend(Storage):
    def download_url(self, instance: models.Model):
        raise NotImplementedError

    # TODO: get_upload_url()
