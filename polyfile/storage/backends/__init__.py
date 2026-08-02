from django import forms
from django.core.files.storage import Storage
from django.db import models
from django.http import HttpRequest


class BaseStorageBackend(Storage):
    name = None

    def download_url(self, instance: models.Model):
        raise NotImplementedError

    def save_file(self, fs_node: models.Model, request: HttpRequest) -> None:
        raise NotImplementedError

    @classmethod
    def get_option_fields(cls) -> dict[str, forms.Field]:
        raise NotImplementedError
