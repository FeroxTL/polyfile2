import uuid

from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob
from polyfile.apps.storage.utils import remove_fs_node


class FsNodeByIdApiTests(TestCase):
    """Pin the contract of `GET/DELETE /api/v1/fs-node/<uuid:node_id>/`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.client.force_login(self.user)

        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )
        self.leaf = FsNodeFileFactory(
            name="leaf.txt", owner=self.user, storage=self.storage, parent=self.sub,
        )

        self.other_user = UserFactory(storage=self.storage)
        self.foreign = FsNodeDirectoryFactory(
            name="foreign", owner=self.other_user, storage=self.storage,
        )

    @staticmethod
    def _url(node_id: uuid.UUID) -> str:
        return reverse("fs_node_by_id", kwargs={"node_id": node_id})

    def test_get_directory_by_id(self) -> None:
        response = self.client.get(self._url(self.sub.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["current"]["id"], str(self.sub.pk))
        self.assertEqual(data["current"]["parent_id"], str(self.root.pk))
        self.assertNotIn("path", data["current"])
        self.assertEqual(data["ancestors"], [{"id": str(self.root.pk), "name": "root"}])
        self.assertEqual([child["name"] for child in data["children"]], ["leaf.txt"])

    def test_get_file_by_id(self) -> None:
        response = self.client.get(self._url(self.leaf.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["current"]["id"], str(self.leaf.pk))
        self.assertNotIn("path", data["current"])
        self.assertEqual(
            data["ancestors"],
            [
                {"id": str(self.root.pk), "name": "root"},
                {"id": str(self.sub.pk), "name": "sub"},
            ],
        )
        self.assertEqual(data["children"], [])

    def test_get_foreign_node_is_not_found(self) -> None:
        self.assertEqual(self.client.get(self._url(self.foreign.pk)).status_code, 404)

    def test_get_tombstoned_node_is_not_found(self) -> None:
        remove_fs_node(self.user, self.root.pk)
        self.assertEqual(self.client.get(self._url(self.sub.pk)).status_code, 404)

    def test_get_unknown_node_is_not_found(self) -> None:
        self.assertEqual(self.client.get(self._url(uuid.uuid4())).status_code, 404)

    def test_get_invalid_uuid_is_not_found(self) -> None:
        self.assertEqual(self.client.get("/api/v1/fs-node/not-a-uuid/").status_code, 404)

    def test_delete_by_id(self) -> None:
        response = self.client.delete(self._url(self.root.pk))
        self.assertEqual(response.status_code, 202)
        data = response.json()
        job = FsNodeDeletionJob.objects.get(pk=data["job_id"])
        self.assertEqual(job.root_node_uuid, self.root.pk)
        self.assertEqual(job.root_node_name, "root")
        self.assertEqual(job.total_nodes, 3)
        self.assertEqual(FsNode.active.filter(owner=self.user).count(), 0)
        # The foreign node is not affected.
        self.assertTrue(FsNode.active.filter(pk=self.foreign.pk).exists())

    def test_delete_by_id_keeps_foreign_node(self) -> None:
        response = self.client.delete(self._url(self.foreign.pk))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(FsNode.active.filter(pk=self.foreign.pk).exists())

    def test_delete_by_id_unknown_is_not_found(self) -> None:
        self.assertEqual(self.client.delete(self._url(uuid.uuid4())).status_code, 404)

    def test_delete_by_id_tombstoned_is_not_found(self) -> None:
        remove_fs_node(self.user, self.root.pk)
        self.assertEqual(self.client.delete(self._url(self.sub.pk)).status_code, 404)


class RemoveFsNodeByIdTests(TestCase):
    """Unit tests for `remove_fs_node`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )

    def test_job_keeps_root_identity(self) -> None:
        job = remove_fs_node(self.user, self.sub.pk)
        self.assertEqual(job.root_node_uuid, self.sub.pk)
        self.assertEqual(job.root_node_name, "sub")
        self.assertEqual(job.total_nodes, 1)
        self.assertIsNotNone(FsNode.objects.get(pk=self.sub.pk).deleted_at)

    def test_shares_are_revoked(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)
        remove_fs_node(self.user, self.root.pk)
        share.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)

    def test_foreign_node_is_not_found(self) -> None:
        other_user = UserFactory(storage=self.storage)
        with self.assertRaises(Exception) as ctx:
            remove_fs_node(other_user, self.root.pk)
        self.assertEqual(getattr(ctx.exception, "status_code", None), 404)
        self.assertTrue(FsNode.active.filter(pk=self.root.pk).exists())
