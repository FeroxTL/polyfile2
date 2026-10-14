import factory

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.models import FsNode, FsStorage
from polyfile.apps.storage.tests import TestFsBackend
from polyfile.contrib.backends.utils import get_storage_path


class StorageFactory(factory.django.DjangoModelFactory):
    """Storage factory."""
    class Meta:
        model = FsStorage
        django_get_or_create = ("backend",)

    backend = get_storage_path(TestFsBackend)
    name = 'Test Storage'


class FsNodeDirectoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FsNode

    storage = factory.SubFactory(StorageFactory)
    type = FsNode.TypeChoices.DIRECTORY
    size = 0
    mime_type = ""
    name = factory.Faker("file_name")
    owner = factory.SubFactory(UserFactory)


class FsNodeFileFactory(FsNodeDirectoryFactory):
    type = FsNode.TypeChoices.FILE
    name = factory.Faker("file_name", extension='')
    size = factory.Faker("random_int")
    mime_type = factory.Faker("mime_type")
