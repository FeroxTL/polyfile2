from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models


class User(AbstractUser):
    """User model."""
    storage = models.ForeignKey(
        'storage.Storage',
        verbose_name='Storage',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    objects = DjangoUserManager()
    storage_id: str | None

    @property
    def full_name(self) -> str:
        """User's full name."""
        return f'{self.first_name} {self.last_name}'.strip() or self.username
