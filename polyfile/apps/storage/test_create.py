import json

from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, TempUpload
from polyfile.apps.storage.utils import create_fs_node, remove_fs_node
from polyfile.core.exceptions import (
    FsNodeExistsError,
    FsNodeIsNotADirectoryError,
    FsNodeNotFoundError,
    InvalidFsNodeName,
)


class CreateFsNodeByNameTests(TestCase):
    """Unit tests for `create_fs_node`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.file = FsNodeFileFactory(name="notes.txt", owner=self.user, storage=self.storage)

    def test_create_in_virtual_root(self) -> None:
        node = create_fs_node(self.user, None, "docs", FsNode.TypeChoices.DIRECTORY)
        self.assertIsNone(node.parent_id)
        self.assertEqual(node.owner, self.user)
        self.assertEqual(node.storage_id, self.storage.pk)

    def test_create_nested(self) -> None:
        node = create_fs_node(
            self.user, self.root.pk, "reports", FsNode.TypeChoices.DIRECTORY,
        )
        self.assertEqual(node.parent_id, self.root.pk)

    def test_duplicate_name_is_rejected(self) -> None:
        with self.assertRaises(FsNodeExistsError):
            create_fs_node(self.user, None, "root", FsNode.TypeChoices.DIRECTORY)

    def test_foreign_parent_is_not_found(self) -> None:
        other_user = UserFactory(storage=self.storage)
        with self.assertRaises(FsNodeNotFoundError):
            create_fs_node(other_user, self.root.pk, "docs", FsNode.TypeChoices.DIRECTORY)

    def test_file_parent_is_rejected(self) -> None:
        with self.assertRaises(FsNodeIsNotADirectoryError):
            create_fs_node(self.user, self.file.pk, "docs", FsNode.TypeChoices.DIRECTORY)

    def test_invalid_names_are_rejected(self) -> None:
        for name in ("", ".", "..", "a/b", "a\\b", "a<b", "a>b", "a:b", 'a"b', "a|b", "a?b", "a*b"):
            with self.assertRaises(InvalidFsNodeName, msg=f"name={name!r}"):
                create_fs_node(self.user, None, name, FsNode.TypeChoices.DIRECTORY)

    def test_too_long_name_is_rejected(self) -> None:
        with self.assertRaises(InvalidFsNodeName):
            create_fs_node(self.user, None, "a" * 256, FsNode.TypeChoices.DIRECTORY)

    def test_recreating_tombstoned_name_is_allowed(self) -> None:
        remove_fs_node(self.user, self.root.pk)
        node = create_fs_node(self.user, None, "root", FsNode.TypeChoices.DIRECTORY)
        self.assertNotEqual(node.pk, self.root.pk)


class FsNodeCreateByNameApiTests(TestCase):
    """API tests for mkdir/touch with `{parent_id, name}` JSON body."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.client.force_login(self.user)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.file = FsNodeFileFactory(name="notes.txt", owner=self.user, storage=self.storage)

    def test_mkdir_in_root_via_body(self) -> None:
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data=json.dumps({"parent_id": None, "name": "docs"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["name"], "docs")
        self.assertEqual(data["type"], FsNode.TypeChoices.DIRECTORY.value)
        self.assertIsNone(data["parent_id"])
        self.assertTrue(FsNode.active.filter(name="docs", owner=self.user).exists())

    def test_mkdir_nested_via_body(self) -> None:
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data=json.dumps({"parent_id": str(self.root.pk), "name": "reports"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["parent_id"], str(self.root.pk))

    def test_mkdir_without_parent_id_creates_in_root(self) -> None:
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data=json.dumps({"name": "docs"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["parent_id"])

    def test_touch_via_body_creates_temp_upload(self) -> None:
        response = self.client.post(
            reverse("fs_node_touch"),
            data=json.dumps({"parent_id": str(self.root.pk), "name": "report.pdf"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["type"], FsNode.TypeChoices.FILE.value)
        self.assertIn("upload_url", data)
        node = FsNode.active.get(name="report.pdf", owner=self.user)
        self.assertTrue(TempUpload.objects.filter(fs_node=node).exists())

    def test_mkdir_foreign_parent_is_not_found(self) -> None:
        other_user = UserFactory(storage=self.storage)
        foreign = FsNodeDirectoryFactory(name="foreign", owner=other_user, storage=self.storage)
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data=json.dumps({"parent_id": str(foreign.pk), "name": "docs"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_mkdir_file_parent_is_rejected(self) -> None:
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data=json.dumps({"parent_id": str(self.file.pk), "name": "docs"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)

    def test_mkdir_invalid_name_is_rejected(self) -> None:
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data=json.dumps({"parent_id": None, "name": "a/b"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_mkdir_invalid_json_is_rejected(self) -> None:
        response = self.client.post(
            reverse("fs_node_mkdir"),
            data="{invalid",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "BadRequest")
