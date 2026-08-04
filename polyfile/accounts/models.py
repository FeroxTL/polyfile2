from django.contrib.auth.models import AbstractUser
from django.db import models
from django_hint import StandardModelType


class User(AbstractUser, StandardModelType['User']):
    """User model."""
    storage = models.ForeignKey(
        'storage.Storage',
        verbose_name='Storage',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    storage_id: str | None

    @property
    def full_name(self) -> str:
        """User's full name."""
        return f'{self.first_name} {self.last_name}'.strip() or self.username
