import logging

from django.apps.registry import apps
from django.core.files.storage import InvalidStorageError, StorageHandler
from django.utils.functional import cached_property

from polyfile.contrib.backends.base import FsBackendBase

logger = logging.getLogger(__name__)


def _get_backend_options() -> dict[str, dict]:
    """Get storages from database."""
    apps.check_models_ready()
    storage_model = apps.get_model(app_label="storage", model_name="FsStorage", require_ready=True)
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
    def backends(self) -> dict[str, dict]:
        if self._backends is None:
            self._backends = _get_backend_options()
        return self._backends or {}

    def clear(self) -> None:
        """Clear all storages and invalidate cache."""
        self._backends = None
        self._storages.clear()
        # Invalidate @cached_property
        self.__dict__.pop("backends", None)


def register_backend(storage_cls: type[FsBackendBase]) -> None:
    """Register storage backend."""
    if not issubclass(storage_cls, FsBackendBase):
        raise InvalidStorageError(f"Invalid backend class {storage_cls!r}: must subclass BaseStorageBackend")

    backend = f"{storage_cls.__module__}.{storage_cls.__name__}"

    if backend in registered_backends:
        logger.warning(f"Backend {backend!r} is already registered")

    registered_backends[backend] = storage_cls


fs_storages = FsStorageHandler()
registered_backends: dict[str, type[FsBackendBase]] = {}
