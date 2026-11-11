import factory
from django.db import models
from django.http.request import HttpRequest

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.models import (
    FsNode,
    FsNodeArchiveItem,
    FsNodeArchiveJob,
    FsStorage,
    PendingObjectDeletion,
)
from polyfile.contrib.backends.base import FsBackendBase
from polyfile.contrib.backends.utils import get_storage_path


class TestFsBackend(FsBackendBase):
    """Backend for testing the storage backend."""

    def download_url(self, instance: models.Model) -> str:
        return "/test/url/"

    def save_file(self, fs_node: models.Model, request: HttpRequest) -> None:
        pass


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
