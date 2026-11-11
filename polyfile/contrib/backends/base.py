"""Base interface for per-node storage backends."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import BinaryIO

from django.db import models


class StorageBackend(ABC):
    """Minimal backend interface for user files.

    Implementations must provide local/S3/... access without relying on
    Django's file-upload forms or public URL semantics.
    """

    name: str | None = None

    @abstractmethod
    def open(self, name: str, mode: str = "rb") -> BinaryIO:
        """Open an existing object."""

    @abstractmethod
    def save(self, name: str, content) -> None:
        """Save ``content`` (a file-like object) under ``name``."""

    @abstractmethod
    def delete(self, name: str) -> None:
        """Delete an object. Missing objects are ignored."""

    @abstractmethod
    def exists(self, name: str) -> bool:
        """Return whether the object exists."""

    @abstractmethod
    def size(self, name: str) -> int:
        """Return object size in bytes."""

    def delete_many(self, names: Iterable[str]) -> dict[str, bool | Exception]:
        """Bulk delete and report per-object results.

        A result of ``True`` means the object was removed or did not exist.
        Any other value indicates a failure, usually an ``Exception``.
        """
        results: dict[str, bool | Exception] = {}
        for name in names:
            try:
                self.delete(name)
            except Exception as exc:  # noqa: BLE001
                results[name] = exc
            else:
                results[name] = True
        return results

    def download_url(self, instance: models.Model) -> str:
        """Return a URL for downloading ``instance``.

        Empty string means "no direct/public URL"; the view layer should serve
        the file itself.
        """
        return ""
