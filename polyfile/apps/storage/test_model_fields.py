import tempfile

from django.core.files.storage import default_storage
from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import FsNodeFileFactory, StorageFactory
from polyfile.apps.storage.model_fields import FsStorageFieldFile
from polyfile.apps.storage.models import FsNode, FsStorage
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path


class FsStorageFieldFileUrlTests(TestCase):
    """`FileField.url` must delegate to the configured backend."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)

    def test_url_delegates_to_backend(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            file="uploads/a.txt",
        )

        self.assertEqual(node.file.url, "/test/url/")
        self.assertEqual(node.file.download_url(), "/test/url/")

    def test_url_is_empty_without_file(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            file="",
        )

        self.assertEqual(node.file.url, "")

    def test_url_is_empty_for_unsaved_node(self) -> None:
        node = FsNode(
            name="new.txt",
            type=FsNode.TypeChoices.FILE,
            owner=self.user,
            storage=self.storage,
            file="uploads/new.txt",
        )

        self.assertTrue(node._state.adding)
        self.assertEqual(node.file.url, "")

    def test_url_is_empty_without_storage(self) -> None:
        node = FsNode(
            name="a.txt",
            type=FsNode.TypeChoices.FILE,
            owner=self.user,
            storage_id=None,
            file="uploads/a.txt",
        )
        file = FsStorageFieldFile(
            node,
            node._meta.get_field("file"),
            "uploads/a.txt",
        )

        self.assertIsNone(file.storage)
        self.assertEqual(file.url, "")

    def test_url_is_empty_for_foreign_storage(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            file="uploads/a.txt",
        )
        file = FsStorageFieldFile(
            node,
            node._meta.get_field("file"),
            "uploads/a.txt",
        )
        file.storage = default_storage

        self.assertEqual(file.url, "")


class FileSystemFieldFileUrlTests(TestCase):
    """The local backend must expose the authorized download view."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = FsStorage.objects.create(
            name="Local disk",
            backend=get_storage_path(FileSystemBackend),
            options={"location": self.temp_dir.name, "upload_to": ""},
        )
        self.user = UserFactory(storage=self.storage)

    def test_url_points_to_download_view(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            file="a.txt",
        )

        self.assertEqual(
            node.file.url,
            reverse("download_file", args=[node.pk]),
        )


class FsNodeAdminFileUrlTests(TestCase):
    """The admin file widget must render a safe link, not a media URL."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.admin = UserFactory(
            storage=self.storage,
            is_staff=True,
            is_superuser=True,
        )
        self.node = FsNodeFileFactory(
            owner=self.admin,
            storage=self.storage,
            file="uploads/a.txt",
        )

    def test_change_form_renders_backend_url(self) -> None:
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse("admin:storage_fsnode_change", args=[self.node.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/test/url/")
