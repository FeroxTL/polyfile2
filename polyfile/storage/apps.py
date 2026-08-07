from django.apps import AppConfig

from polyfile.storage.handler import register_backend


class StorageConfig(AppConfig):
    name = "polyfile.storage"

    def ready(self) -> None:
        import polyfile.storage.signals  # noqa
        from polyfile.backends.file_system_backend.backend import FileSystemBackend
        register_backend(FileSystemBackend)
