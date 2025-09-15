from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from polyfile.storage.handler import fs_storages
from polyfile.storage.models import Storage


@receiver([post_save, post_delete], sender=Storage)
def _invalidate_storages(**kwargs) -> None:
    """Invalidate storages caches."""
    # TODO: remove clear (slow); separate addition and deletion
    fs_storages.clear()
