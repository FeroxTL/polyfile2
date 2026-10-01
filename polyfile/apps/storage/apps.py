from django.apps import AppConfig

from polyfile.apps.storage.handler import register_backend


class StorageConfig(AppConfig):
    name = "polyfile.apps.storage"

    def ready(self) -> None:
        import polyfile.apps.storage.signals  # noqa
        from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
        register_backend(FileSystemBackend)
