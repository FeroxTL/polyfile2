from django.apps import AppConfig

from polyfile.storage.backends.local_path_backend import LocalDiskBackend
from polyfile.storage.handler import register_backend


class StorageConfig(AppConfig):
    name = "polyfile.storage"

    def ready(self) -> None:  # noqa
        import polyfile.storage.signals # noqa
        register_backend(LocalDiskBackend)
