from django.db import models
from django.http.request import HttpRequest

from polyfile.contrib.backends.base import FsBackendBase


class TestFsBackend(FsBackendBase):
    """Backend for testing the storage backend."""

    def download_url(self, instance: models.Model):
        pass

    def save_file(self, fs_node: models.Model, request: HttpRequest) -> None:
        pass
