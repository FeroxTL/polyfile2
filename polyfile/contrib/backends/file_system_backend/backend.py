"""Local filesystem storage backend for user files."""

import os
import shutil
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from django.core.exceptions import ValidationError
from django.core.files.utils import validate_file_name
from django.db import models
from django.urls import reverse

from polyfile.contrib.backends.base import StorageBackend


class FileSystemBackend(StorageBackend):
    """Stores files in a directory on the local device."""

    name = "Local file system"
    chunk_size = 64 * 1024

    def __init__(self, location: str | None = None, upload_to: str = "") -> None:
        if not location:
            raise ValidationError({"location": "This field is required!"})
        self.root = Path(location).expanduser().resolve()
        self.upload_to = upload_to

    def _path(self, name: str) -> Path:
        """Resolve ``name`` inside the backend root and reject traversal."""
        relative = PurePosixPath(validate_file_name(name, allow_relative_path=True))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid object key: {name!r}")
        path = (self.root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Object key escapes the storage root: {name!r}")
        return path

    def open(self, name: str, mode: str = "rb") -> BinaryIO:
        return self._path(name).open(mode)

    def save(self, name: str, content) -> None:
        """Atomically publish ``content`` under ``name``.

        Writes to a ``.part`` file, fsyncs it, then replaces the target.
        """
        destination = self._path(name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        try:
            with partial.open("wb") as target:
                shutil.copyfileobj(content, target, length=self.chunk_size)
                target.flush()
                os.fsync(target.fileno())
            os.replace(partial, destination)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)
        self._path(name).with_name(Path(name).name + ".part").unlink(missing_ok=True)

    def exists(self, name: str) -> bool:
        return self._path(name).is_file()

    def size(self, name: str) -> int:
        return self._path(name).stat().st_size

    def download_url(self, instance: models.Model) -> str:
        return reverse("download_file", kwargs={"pk": instance.pk})
