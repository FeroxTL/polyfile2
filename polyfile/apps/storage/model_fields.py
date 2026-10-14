from collections.abc import Sequence
from typing import Any

from django.db import models
from django.db.models.fields.files import FieldFile

from polyfile.apps.storage import models as fs_models
from polyfile.apps.storage.handler import fs_storages
from polyfile.contrib.backends.base import FsBackendBase


class FsStorageFieldFile(FieldFile):
    """File field with dynamic storage."""
    instance: "fs_models.FsNode"  # TODO: define FsNodeProtocol here?

    def __init__(self, instance: "fs_models.FsNode", field: models.FileField, name: str):
        super().__init__(instance, field, name)
        # self.storage is None in non-existent nodes, like root node
        self.storage: FsBackendBase | None = None
        if instance.storage_id:
            self.storage = fs_storages[instance.storage_id]

    def download_url(self) -> str:
        """Public url."""
        # TODO: cache?
        return self.storage.download_url(self.instance)


class FsStorageFileField(models.FileField):
    """File field with dynamic storage selection (based on FsNode storage)."""
    attr_class = FsStorageFieldFile
    # TODO: set default_storage here to return error on any upload

    def pre_save(self, model_instance: "fs_models.FsNode", add: bool):
        """Pre-save hook for field."""
        storage = fs_storages[model_instance.storage_id]
        model_instance.file.storage = self.storage = storage
        return super().pre_save(model_instance, add)

    def deconstruct(self) -> tuple[str, str, Sequence[Any], dict[str, Any]]:
        """Get rid of some fields in django migrations."""
        name, path, args, kwargs = super().deconstruct()
        for field_name in ("storage", "upload_to"):
            kwargs.pop(field_name, None)
        return name, path, args, kwargs
