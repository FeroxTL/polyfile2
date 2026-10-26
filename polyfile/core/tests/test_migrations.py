from io import StringIO

from django.core.management import call_command
from django.test import TestCase


class MigrationsTests(TestCase):
    def test_no_missing_migrations(self) -> None:
        """Fail when a model change has no corresponding migration."""
        stdout = StringIO()
        stderr = StringIO()
        try:
            call_command(
                "makemigrations",
                check=True,
                dry_run=True,
                interactive=False,
                stdout=stdout,
                stderr=stderr,
            )
        except SystemExit as exc:
            self.fail(
                f"makemigrations exited with code {exc.code}. "
                "Model changes are missing migrations:\n"
                f"{stdout.getvalue()}{stderr.getvalue()}"
            )
