"""Storage backends for built directory archives.

Archives are deliberately kept out of ``MEDIA_ROOT``/``FsStorage``: they are
temporary artifacts with a different lifecycle and different access rules.
The MVP uses a local directory and atomically publishes a completed ZIP with
``os.replace``; the interface leaves room for an S3 backend later.
"""

import os
import shutil
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from django.conf import settings


class ArchiveBackend(ABC):
    """Interface for storing and reading built archives."""

    @abstractmethod
    def open(self, key: str) -> BinaryIO:
        """Open an existing archive for reading."""

    @abstractmethod
    def open_for_write(self, key: str) -> AbstractContextManager[BinaryIO]:
        """Yield a writable file object and publish the archive on clean exit."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete an archive. Missing archives are ignored."""

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return whether an archive exists."""

    @abstractmethod
    def size(self, key: str) -> int:
        """Return the archive size in bytes."""

    def save_stream(self, key: str, fileobj: BinaryIO) -> None:
        """Copy ``fileobj`` into an archive and publish it atomically."""
        with self.open_for_write(key) as target:
            shutil.copyfileobj(fileobj, target, length=1024 * 1024)

    def delivery_url(self, key: str, ttl: int) -> str | None:
        """Return a direct delivery URL, or ``None`` to serve via Django/nginx."""
        return None


class FileSystemArchiveBackend(ArchiveBackend):
    """Local archive backend rooted at ``ARCHIVE_ROOT``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def path(self, key: str) -> Path:
        """Resolve an archive key and reject paths outside the archive root."""
        relative = PurePosixPath(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid archive key: {key!r}")

        root = self.root.resolve()
        path = (root / Path(*relative.parts)).resolve()
        if not path.is_relative_to(root):
            raise ValueError(f"Archive key escapes the archive root: {key!r}")
        return path

    def open(self, key: str) -> BinaryIO:
        return self.path(key).open("rb")

    @contextmanager
    def open_for_write(self, key: str) -> Iterator[BinaryIO]:
        destination = self.path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".part")
        try:
            with partial.open("wb") as fileobj:
                yield fileobj
                fileobj.flush()
                os.fsync(fileobj.fileno())
            os.replace(partial, destination)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    def delete(self, key: str) -> None:
        path = self.path(key)
        path.unlink(missing_ok=True)
        path.with_name(path.name + ".part").unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def size(self, key: str) -> int:
        return self.path(key).stat().st_size


def get_archive_backend() -> ArchiveBackend:
    """Return the configured archive backend.

    The MVP has a single local backend. Reading settings lazily keeps
    ``override_settings`` (and future runtime reconfiguration) working.
    """
    return FileSystemArchiveBackend(settings.ARCHIVE_ROOT)
