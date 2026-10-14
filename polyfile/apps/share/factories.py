from datetime import timedelta

import factory
from django.utils import timezone

from polyfile.apps.share.models import SharedNode
from polyfile.apps.storage.factories import FsNodeDirectoryFactory


class SharedNodeFactory(factory.django.DjangoModelFactory):
    """SharedNode factory."""
    class Meta:
        model = SharedNode

    token = factory.Faker("uuid4")
    root_fs_node = factory.SubFactory(FsNodeDirectoryFactory)
    owner = factory.SelfAttribute("root_fs_node.owner")

    expires_at = factory.LazyAttribute(lambda _: timezone.now() + timedelta(days=1))
    revoked_at = None
