"""Tests for the object key built at upload time.

The key must be unique per physical object so that the deletion worker cannot
remove a file that still belongs to another (or a re-uploaded) node.
"""

import tempfile
from datetime import datetime

from django.test import TestCase
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
)
from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.models import FsNode, FsStorage
from polyfile.apps.storage.upload_service import _build_object_key
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path


class BuildObjectKeyTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = FsStorage.objects.create(
            name="Local disk",
            backend=get_storage_path(FileSystemBackend),
            options={"location": self.temp_dir.name, "upload_to": "%Y/%m/%d"},
        )
        fs_storages.clear()
        self.addCleanup(fs_storages.clear)

        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(
            name="root",
            owner=self.user,
            storage=self.storage,
        )

    def _create_file(self, name: str, parent=None):
        return FsNodeFileFactory(
            name=name,
            object_key="",
            owner=self.user,
            storage=self.storage,
            parent=parent or self.root,
        )

    def test_key_contains_date_prefix_uuid_and_name(self) -> None:
        node = self._create_file("report.txt")

        key = _build_object_key(node)

        self.assertEqual(
            key,
            f"{datetime.now().strftime('%Y/%m/%d')}/{node.pk}-report.txt",
        )

    def test_same_name_in_different_directories_gets_distinct_keys(self) -> None:
        other_dir = FsNodeDirectoryFactory(
            name="other",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        first = self._create_file("report.txt")
        second = self._create_file("report.txt", parent=other_dir)

        self.assertNotEqual(_build_object_key(first), _build_object_key(second))

    def test_delete_and_reupload_gets_a_new_key(self) -> None:
        # The old node is tombstoned (its physical object is queued for
        # deletion); the re-uploaded file must live under a different key so
        # the pending deletion cannot remove it.
        original = self._create_file("setup.exe")
        original_key = _build_object_key(original)
        FsNode.objects.filter(pk=original.pk).update(deleted_at=now())

        reuploaded = self._create_file("setup.exe")

        self.assertNotEqual(original_key, _build_object_key(reuploaded))

    def test_rename_keeps_the_stored_object_key(self) -> None:
        # The key is built once at upload time and stored on the node;
        # renaming the node must not invalidate the physical object.
        node = self._create_file("old-name.txt")
        node.object_key = _build_object_key(node)

        node.name = "new-name.txt"
        node.save(update_fields=["name"])

        self.assertTrue(node.object_key.endswith("-old-name.txt"))

    def test_key_without_upload_to(self) -> None:
        storage = FsStorage.objects.create(
            name="Flat",
            backend=get_storage_path(FileSystemBackend),
            options={"location": self.temp_dir.name, "upload_to": ""},
        )
        fs_storages.clear()
        node = self._create_file("flat.txt")
        node.storage = storage

        self.assertEqual(_build_object_key(node), f"{node.pk}-flat.txt")
