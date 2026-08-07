from django.apps import AppConfig


class BackendConfig(AppConfig):
    name = 'polyfile.backends'

    def ready(self) -> None:
        import polyfile.backends.file_system_backend.admin  # noqa
