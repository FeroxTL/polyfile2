import factory

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.models import (
    FsNode,
    FsNodeArchiveItem,
    FsNodeArchiveJob,
    FsStorage,
    PendingObjectDeletion,
)
from polyfile.contrib.backends.base import StorageBackend
from polyfile.contrib.backends.utils import get_storage_path


class TestFsBackend(StorageBackend):
    """Backend for testing the storage backend."""

    name = "Test storage"

    def __init__(self, **kwargs):
        self.options = kwargs

    def open(self, name: str, mode: str = "rb"):
        raise NotImplementedError

    def save(self, name: str, content):
        pass

    def delete(self, name: str):
        pass

    def exists(self, name: str):
        return False

    def size(self, name: str):
        return 0

    def download_url(self, instance) -> str:
        return "/test/url/"


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


class PendingObjectDeletionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = PendingObjectDeletion

    storage_id = factory.Sequence(lambda n: n + 1)
    object_key = factory.Sequence(lambda n: f"uploads/{n}/file.txt")
    node_uuid = factory.Faker("uuid4")


class FsNodeArchiveJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FsNodeArchiveJob

    requested_by = factory.SubFactory(UserFactory)
    root_node_uuid = factory.Faker("uuid4")
    root_node_name = "root"
    fingerprint = factory.Faker("uuid4")


class FsNodeArchiveItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = FsNodeArchiveItem

    job = factory.SubFactory(FsNodeArchiveJobFactory)
    node = factory.SubFactory(FsNodeFileFactory)
    entry_type = FsNodeArchiveItem.EntryType.FILE
    zip_path = factory.Sequence(lambda n: f"file-{n}.txt")
    object_key = factory.Sequence(lambda n: f"uploads/{n}/file.txt")
    storage_id = factory.LazyAttribute(lambda o: o.node.storage_id)
    size = factory.LazyAttribute(lambda o: o.node.size)
    md5 = factory.LazyAttribute(lambda o: o.node.md5)
    modified_at = factory.LazyAttribute(lambda o: o.node.modified_at)
    position = factory.Sequence(lambda n: n)
