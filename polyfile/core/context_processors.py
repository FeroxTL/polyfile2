"""Template context processors shared by all templates."""
from django.conf import settings
from django.http import HttpRequest


def settings_context(request: HttpRequest) -> dict[str, object]:
    """Expose some settings values to every template."""
    return {
        "DEBUG": getattr(settings, "DEBUG", True),
    }
