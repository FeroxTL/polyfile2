import logging
from typing import Type

from django.apps.registry import apps
from django.core.files.storage import StorageHandler, InvalidStorageError
from django.utils.functional import cached_property

from polyfile.storage.backends import BaseStorageBackend


def _get_backend_options() -> dict[str, dict]:
    """Get storages from database."""
    apps.check_models_ready()
    storage_model = apps.get_model(app_label="storage", model_name="Storage", require_ready=True)
    return {
        instance.id: {
            "BACKEND": instance.backend,
            "OPTIONS": instance.options,
        } for instance in storage_model.objects.values_list('id', 'backend', 'options', named=True)
    }


class FsStorageHandler(StorageHandler):
    _backends: dict | None
    _storages: dict

    @cached_property
    def backends(self) -> None:
        if self._backends is None:
            self._backends = _get_backend_options()
        return self._backends

    def clear(self) -> None:
        """Clear all storages and invalidate cache."""
        self._backends = None
        self._storages.clear()
        # Invalidate @cached_property
        self.__dict__.pop("backends", None)


def register_backend(storage_cls: Type[BaseStorageBackend], name: str = "") -> None:
    """Register storage backend."""
    if not issubclass(storage_cls, BaseStorageBackend):
        raise InvalidStorageError(f"Invalid backend class {storage_cls!r}: must subclass BaseStorageBackend")

    backend = f"{storage_cls.__module__}.{storage_cls.__name__}"

    if backend in registered_backends:
        logging.warning(f"Backend {backend!r} is already registered")

    registered_backends[backend] = name or storage_cls.__name__


fs_storages = FsStorageHandler()
registered_backends: dict[str, str] = {}
