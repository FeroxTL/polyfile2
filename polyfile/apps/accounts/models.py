import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Final

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django_hint import StandardModelType

API_KEY_TOKEN_PREFIX: Final[str] = "pf"
API_KEY_PREFIX_BYTES: Final[int] = 6
API_KEY_SECRET_BYTES: Final[int] = 32
API_KEY_LAST_USED_UPDATE_INTERVAL: Final[timedelta] = timedelta(minutes=1)


class User(AbstractUser, StandardModelType['User']):
    """User model."""
    storage = models.ForeignKey(
        'storage.FsStorage',
        verbose_name='Storage',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    id: int | None
    storage_id: str | None

    @property
    def full_name(self) -> str:
        """User's full name."""
        return f'{self.first_name} {self.last_name}'.strip() or self.username


class ApiKey(models.Model, StandardModelType["ApiKey"]):
    """Hashed API credential owned by a user.

    The plaintext token is returned exactly once by ``create_for_user``. Only
    its HMAC digest and a short public prefix are stored, so a database leak
    does not expose usable credentials.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    name = models.CharField(max_length=64)
    prefix = models.CharField(max_length=32, unique=True, editable=False)
    key_hash = models.CharField(max_length=64, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "API key"
        verbose_name_plural = "API keys"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.name} ({self.prefix})"

    @property
    @admin.display(boolean=True, description="Active")
    def is_active(self) -> bool:
        """Return whether the key may be used for authentication."""
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > timezone.now()

    def revoke(self) -> None:
        """Revoke the key without deleting its audit trail."""
        if self.revoked_at is None:
            self.revoked_at = timezone.now()
            self.save(update_fields=("revoked_at",))

    def mark_used(self) -> None:
        """Update ``last_used_at`` at most once per minute.

        API keys are used for every request in load tests, so writing on each
        request would add avoidable database contention.
        """
        current_time = timezone.now()
        if (
            self.last_used_at is not None
            and current_time - self.last_used_at < API_KEY_LAST_USED_UPDATE_INTERVAL
        ):
            return
        self.last_used_at = current_time
        self.save(update_fields=("last_used_at",))

    @classmethod
    def create_for_user(
        cls,
        user: User,
        name: str,
        *,
        expires_at: datetime | None = None,
    ) -> tuple["ApiKey", str]:
        """Create a key and return ``(api_key, plaintext_token)``."""
        prefix = secrets.token_hex(API_KEY_PREFIX_BYTES)
        secret = secrets.token_urlsafe(API_KEY_SECRET_BYTES)
        token = f"{API_KEY_TOKEN_PREFIX}_{prefix}_{secret}"
        api_key = cls.objects.create(
            user=user,
            name=name,
            prefix=prefix,
            key_hash=cls.hash_token(token),
            expires_at=expires_at,
        )
        return api_key, token

    @staticmethod
    def hash_token(token: str) -> str:
        """Return the stored HMAC digest for a plaintext token."""
        hash_key = getattr(settings, "API_KEY_HASH_KEY", settings.SECRET_KEY)
        return hmac.new(
            hash_key.encode("utf-8"),
            token.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    def parse_token(token: str) -> tuple[str, str] | None:
        """Split a token into ``(prefix, secret)`` or return ``None``."""
        parts = token.split("_", 2)
        if (
            len(parts) != 3
            or parts[0] != API_KEY_TOKEN_PREFIX
            or not parts[1]
            or not parts[2]
        ):
            return None
        return parts[1], parts[2]

    @classmethod
    def authenticate(cls, token: str) -> "ApiKey | None":
        """Return the active key for ``token``, or ``None`` when invalid."""
        parsed = cls.parse_token(token)
        if parsed is None:
            return None

        prefix, _secret = parsed
        api_key = cls.objects.select_related("user").filter(prefix=prefix).first()
        if api_key is None:
            return None
        if not hmac.compare_digest(api_key.key_hash, cls.hash_token(token)):
            return None
        if not api_key.is_active or not api_key.user.is_active:
            return None
        return api_key
