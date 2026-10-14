from django.core.files.storage import Storage
from django.db import models
from django.http import HttpRequest


class FsBackendBase(Storage):
    name = None

    def download_url(self, instance: models.Model):
        raise NotImplementedError

    def save_file(self, fs_node: models.Model, request: HttpRequest) -> None:
        raise NotImplementedError
