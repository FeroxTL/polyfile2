from django.apps import AppConfig


class BackendConfig(AppConfig):
    name = 'polyfile.contrib.backends'

    def ready(self) -> None:
        import polyfile.contrib.backends.file_system_backend.admin  # noqa
