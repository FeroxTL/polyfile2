import datetime

from django.conf import settings
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.http import base36_to_int, int_to_base36
from django.utils import timezone


class FileDownloadTokenGenerator:
    """
    Strategy object used to generate and check tokens for the file download mechanism.

    Based on `django.contrib.auth.tokens.PasswordResetTokenGenerator`.
    """

    key_salt = "polyfile.storage.tokens.FileDownloadTokenGenerator"
    algorithm = "sha256"

    @property
    def secret(self) -> str:
        """Secret key."""
        return settings.SECRET_KEY

    @property
    def secret_fallbacks(self) -> list[str] | tuple[str]:
        """Secret key fallbacks."""
        return settings.SECRET_KEY_FALLBACKS

    @property
    def timeout_sec(self) -> int:
        # TODO: custom settings
        return settings.PASSWORD_RESET_TIMEOUT

    def make_token(self, fs_node):
        """Return a token that can be used to download given file."""
        return self._make_token_with_timestamp(
            fs_node=fs_node,
            timestamp=self._num_seconds(self._now()),
            secret=self.secret,
        )

    def check_token(self, fs_node, token: str):
        """Check that a password reset token is correct for a given user."""
        if not (fs_node and token):
            return False
        # Parse the token
        try:
            ts_b36, _ = token.split('-')
        except ValueError:
            return False

        try:
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False

        # Check that the timestamp/uid has not been tampered with
        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(
                self._make_token_with_timestamp(fs_node, ts, secret),
                token,
            ):
                break
        else:
            return False

        # Check the timestamp is within limit.
        return (self._num_seconds(self._now()) - ts) <= self.timeout_sec

    def _make_token_with_timestamp(self, fs_node, timestamp: int, secret: str):
        # timestamp is number of seconds since 2001-1-1. Converted to base 36,
        # this gives us a 6 digit string until about 2069.
        ts_b36 = int_to_base36(timestamp)
        hash_string = salted_hmac(
            self.key_salt,
            self._make_hash_value(fs_node, timestamp),
            secret=secret,
            algorithm=self.algorithm,
        ).hexdigest()[
            ::2
        ]  # Limit to shorten the URL.
        return f'{ts_b36}-{hash_string}'

    @staticmethod
    def _make_hash_value(fs_node, timestamp: int):
        """
        Hash the fs_node's primary key, storage_id, and md5 sum.

        Running this data through salted_hmac() prevents password cracking
        attempts using the token, provided the secret isn't compromised.
        """
        return f'{fs_node.id}{fs_node.storage_id}{timestamp}{fs_node.md5}'

    @staticmethod
    def _num_seconds(dt: datetime.datetime) -> int:
        return int((dt - datetime.datetime(2001, 1, 1, tzinfo=datetime.UTC)).total_seconds())

    @staticmethod
    def _now() -> datetime.datetime:
        # Used for mocking in tests TODO: check
        return timezone.now()


default_token_generator = FileDownloadTokenGenerator()
