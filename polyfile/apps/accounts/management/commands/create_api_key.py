"""Create an API key and print its plaintext token exactly once."""

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now

from polyfile.apps.accounts.models import ApiKey, User
from polyfile.core.utils import parse_duration


class Command(BaseCommand):
    """Create a user API key for scripts and load tests."""

    help = "Create an API key for a user and print the token once."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--username", required=True, help="Owner username")
        parser.add_argument("--name", required=True, help="Human-readable key name")
        parser.add_argument(
            "--expires-in",
            dest="expires_in",
            default=None,
            help="Optional lifetime such as 30s, 15m, 24h or 7d",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print a JSON object instead of human-readable text",
        )

    def handle(self, *args, **options) -> None:
        try:
            user = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError(
                f'User "{options["username"]}" does not exist.',
            ) from exc

        expires_at = None
        if options["expires_in"]:
            try:
                expires_at = now() + parse_duration(options["expires_in"])
            except ValueError as exc:
                raise CommandError(str(exc)) from exc

        api_key, token = ApiKey.create_for_user(
            user,
            options["name"],
            expires_at=expires_at,
        )

        payload = {
            "id": str(api_key.pk),
            "name": api_key.name,
            "prefix": api_key.prefix,
            "token": token,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

        if options["json"]:
            self.stdout.write(json.dumps(payload))
            return

        self.stdout.write(
            self.style.SUCCESS(
                "API key created. Copy the token now; it will not be shown again.",
            ),
        )
        self.stdout.write(f"id: {payload['id']}")
        self.stdout.write(f"name: {payload['name']}")
        self.stdout.write(f"prefix: {payload['prefix']}")
        self.stdout.write(f"expires_at: {payload['expires_at'] or 'never'}")
        self.stdout.write(token)
