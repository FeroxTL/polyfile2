from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.models import FsStorage


@receiver([post_save, post_delete])
def _invalidate_storages(sender, **kwargs) -> None:
    """Invalidate storages caches."""
    if issubclass(sender, FsStorage):
        fs_storages.clear()
