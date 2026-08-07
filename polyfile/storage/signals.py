from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from polyfile.storage.handler import fs_storages
from polyfile.storage.models import Storage


@receiver([post_save, post_delete])
def _invalidate_storages(sender, **kwargs) -> None:
    """Invalidate storages caches."""
    if issubclass(sender, Storage):
        fs_storages.clear()
