"""Composite field that exposes a single ``file`` attribute backed by two DB columns.

The real data lives in ``storage_id`` (FK to ``FsStorage``) and ``object_key``
(path inside the selected storage). ``FileRefField`` is a descriptor factory
that returns ``FsNodeFileRef``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, BinaryIO

from polyfile.apps.storage.handler import fs_storages
from polyfile.contrib.backends.base import StorageBackend

if TYPE_CHECKING:
    from polyfile.apps.storage import models as fs_models


class FsNodeFileRef:
    """Reference to a physical file object: storage + key."""

    __slots__ = ("instance", "object_key", "storage_id")

    def __init__(self, instance: fs_models.FsNode, storage_id: int | None, object_key: str):
        self.instance: fs_models.FsNode = instance
        self.storage_id = storage_id
        self.object_key = object_key

    def __bool__(self) -> bool:
        return bool(self.object_key)

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"storage_id={self.storage_id}, object_key={self.object_key!r})"
        )

    @property
    def backend(self) -> StorageBackend | None:
        if self.storage_id is None:
            return None
        return fs_storages[self.storage_id]

    def open(self, mode: str = "rb") -> BinaryIO:
        """Open the physical file."""
        backend = self.backend
        if backend is None:
            raise RuntimeError("Cannot open file: storage_id is not set")
        return backend.open(self.object_key, mode)

    def delete(self) -> None:
        """Delete the physical file."""
        backend = self.backend
        if backend is None or not self.object_key:
            return
        backend.delete(self.object_key)

    def download_url(self) -> str:
        """Return a URL that can be used to download the file."""
        backend = self.backend
        if backend is None or not self.object_key:
            return ""
        return backend.download_url(self.instance)


class FsNodeFileDescriptor:
    """Descriptor that returns/sets an ``FsNodeFileRef``."""

    def __init__(self, storage_id_field: str, object_key_field: str):
        self.storage_id_field = storage_id_field
        self.object_key_field = object_key_field

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        storage_id = getattr(instance, self.storage_id_field)
        object_key = getattr(instance, self.object_key_field) or ""
        return FsNodeFileRef(instance, storage_id, object_key)

    def __set__(self, instance, value: FsNodeFileRef | None):
        if value is None:
            setattr(instance, self.object_key_field, "")
        elif isinstance(value, FsNodeFileRef):
            setattr(instance, self.storage_id_field, value.storage_id)
            setattr(instance, self.object_key_field, value.object_key)
        else:
            raise TypeError(
                f"Expected FsNodeFileRef or None, got {type(value).__name__}"
            )


class FileRefField:
    """Descriptor factory that exposes a composite ``file`` attribute.

    The actual columns are declared separately (e.g. ``storage_id`` and
    ``object_key``). This class is **not** a Django ``Field``; it exists only
    in Python and is invisible to migrations, forms and the ORM.
    """

    def __init__(self, storage_id_field: str, object_key_field: str, **kwargs):
        self.storage_id_field = storage_id_field
        self.object_key_field = object_key_field
        self.editable = kwargs.get("editable", False)
        self.blank = kwargs.get("blank", True)
        self.verbose_name = kwargs.get("verbose_name", "")
        self.name: str | None = None
        self.attname: str | None = None

    def contribute_to_class(self, cls, name: str, private_only: bool = False):
        self.name = name
        self.attname = name
        descriptor = FsNodeFileDescriptor(self.storage_id_field, self.object_key_field)
        setattr(cls, name, descriptor)

    def __set_name__(self, owner, name):
        self.name = name
        self.attname = name
