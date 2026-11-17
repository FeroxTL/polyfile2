import json

from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, PendingObjectDeletion, TempUpload
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
        with self.assertRaises(FsNodeExistsError) as ctx:
            create_fs_node(self.user, None, "root", FsNode.TypeChoices.DIRECTORY)
        self.assertEqual(ctx.exception.extra["existing_node_id"], str(self.root.pk))
        self.assertEqual(ctx.exception.extra["existing_type"], FsNode.TypeChoices.DIRECTORY)

    def test_replace_reuses_an_existing_file(self) -> None:
        node = create_fs_node(
            self.user, None, "notes.txt", FsNode.TypeChoices.FILE, replace=True,
        )

        self.assertEqual(node.pk, self.file.pk)

    def test_replace_does_not_reuse_a_directory(self) -> None:
        with self.assertRaises(FsNodeExistsError) as ctx:
            create_fs_node(
                self.user, None, "root", FsNode.TypeChoices.FILE, replace=True,
            )

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(self.root.pk))
        self.assertEqual(ctx.exception.extra["existing_type"], FsNode.TypeChoices.DIRECTORY)

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

    def test_touch_conflict_reports_the_existing_node(self) -> None:
        response = self.client.post(
            reverse("fs_node_touch"),
            data=json.dumps({"parent_id": None, "name": "notes.txt"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["error_id"], "FsNodeExistsError")
        self.assertEqual(data["existing_node_id"], str(self.file.pk))
        self.assertEqual(data["existing_type"], FsNode.TypeChoices.FILE)

    def test_touch_replace_reuses_the_file_and_refreshes_temp_upload(self) -> None:
        temp_upload = TempUpload.objects.create(fs_node=self.file)
        temp_upload.mark_complete()
        old_token = temp_upload.token

        response = self.client.post(
            reverse("fs_node_touch"),
            data=json.dumps({"parent_id": None, "name": "notes.txt", "replace": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["id"], str(self.file.pk))
        self.assertIn("upload_url", data)

        temp_upload.refresh_from_db()
        self.assertNotEqual(temp_upload.token, old_token)
        self.assertEqual(temp_upload.status, TempUpload.Status.UPLOADING)
        self.assertIsNone(temp_upload.completed_on)

    def test_touch_replace_rejects_a_directory_with_the_same_name(self) -> None:
        response = self.client.post(
            reverse("fs_node_touch"),
            data=json.dumps({"parent_id": None, "name": "root", "replace": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["existing_node_id"], str(self.root.pk))
        self.assertEqual(data["existing_type"], FsNode.TypeChoices.DIRECTORY)

    def test_upload_replaces_content_and_queues_the_old_object(self) -> None:
        old_object_key = "uploads/old-notes.txt"
        FsNode.objects.filter(pk=self.file.pk).update(object_key=old_object_key)
        temp_upload = TempUpload.objects.create(fs_node=self.file)

        response = self.client.post(
            reverse("upload_file", kwargs={"token": temp_upload.token}),
            data=b"replacement content",
            content_type="application/octet-stream",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.file.refresh_from_db()
        self.assertEqual(self.file.size, len(b"replacement content"))
        self.assertNotEqual(self.file.object_key, old_object_key)
        self.assertTrue(PendingObjectDeletion.objects.filter(
            storage_id=self.storage.pk,
            object_key=old_object_key,
        ).exists())
