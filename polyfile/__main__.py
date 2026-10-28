"""Allow running Polyfile management commands with ``python -m polyfile``."""

import os
import sys


def main(argv: list[str] | None = None) -> None:
    """Run a Django management command using the bundled settings."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "polyfile.core.settings")

    from django.core.management import execute_from_command_line

    execute_from_command_line(
        [sys.argv[0], *(sys.argv[1:] if argv is None else argv)]
    )


if __name__ == "__main__":
    main()
