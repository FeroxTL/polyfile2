from collections.abc import Iterable

from django.core.files.storage import Storage
from django.db import models
from django.http import HttpRequest


class FsBackendBase(Storage):
    """Base class for all types backends."""
    name = None

    def download_url(self, instance: models.Model) -> str:
        """Generate a URL for downloading a file. Must be implemented by subclasses."""
        raise NotImplementedError

    def save_file(self, fs_node: models.Model, request: HttpRequest) -> None:
        """Save a file to the backend. Must be implemented by subclasses."""
        raise NotImplementedError

    def delete_many(self, names: Iterable[str]) -> dict[str, bool | Exception]:
        """Bulk delete files and report per-file results.

        Default implementation deletes files one by one via :meth:`delete`.
        Subclasses may override this with a more efficient bulk operation.

        Returns a mapping of ``{name: result}``. A result of ``True`` means the
        file was successfully removed (or did not exist). Any other value
        indicates a failure and is typically an ``Exception`` describing the
        problem.
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
