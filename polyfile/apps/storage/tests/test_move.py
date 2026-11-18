import json
import uuid
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, FsStorage
from polyfile.apps.storage.trash_service import trash_fs_node
from polyfile.apps.storage.utils import move_fs_node
from polyfile.core.exceptions import (
    FsNodeExistsError,
    FsNodeIsNotADirectoryError,
    FsNodeMoveError,
    FsNodeNotFoundError,
)


class MoveFsNodeTests(TestCase):
    """Unit tests for `move_fs_node`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(
            name="root",
            owner=self.user,
            storage=self.storage,
        )
        self.other = FsNodeDirectoryFactory(
            name="other",
            owner=self.user,
            storage=self.storage,
        )
        self.sub = FsNodeDirectoryFactory(
            name="sub",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        self.file = FsNodeFileFactory(
            name="leaf.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

    def test_moves_file_to_another_directory(self) -> None:
        moved = move_fs_node(self.user, self.file.pk, self.other.pk)

        self.assertEqual(moved.pk, self.file.pk)
        self.assertEqual(moved.parent_id, self.other.pk)
        self.assertEqual(moved.name, "leaf.txt")
        self.assertEqual(moved.type, FsNode.TypeChoices.FILE)
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).parent_id,
            self.other.pk,
        )
        self.assertFalse(
            FsNode.active.filter(parent=self.sub, pk=self.file.pk).exists(),
        )

    def test_moves_directory_with_children(self) -> None:
        moved = move_fs_node(self.user, self.sub.pk, self.other.pk)

        self.assertEqual(moved.parent_id, self.other.pk)
        self.assertEqual(
            FsNode.active.get(pk=self.sub.pk).parent_id,
            self.other.pk,
        )
        # The subtree follows the directory without touching the child.
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).parent_id,
            self.sub.pk,
        )

    def test_moves_root_node_into_another_root(self) -> None:
        moved = move_fs_node(self.user, self.root.pk, self.other.pk)

        self.assertEqual(moved.parent_id, self.other.pk)
        self.assertEqual(
            FsNode.active.get(pk=self.sub.pk).parent_id,
            self.root.pk,
        )

    def test_moves_nested_node_to_virtual_root(self) -> None:
        moved = move_fs_node(self.user, self.file.pk, None)

        self.assertIsNone(moved.parent_id)
        self.assertIsNone(FsNode.active.get(pk=self.file.pk).parent_id)

    def test_moving_to_the_same_parent_is_a_noop(self) -> None:
        with mock.patch.object(FsNode, "save") as save:
            moved = move_fs_node(self.user, self.file.pk, self.sub.pk)

        save.assert_not_called()
        self.assertEqual(moved.pk, self.file.pk)
        self.assertEqual(moved.parent_id, self.sub.pk)

    def test_move_keeps_object_key_and_modified_at(self) -> None:
        object_key = "2026/01/01/leaf.txt"
        self.file.object_key = object_key
        self.file.save(update_fields=("object_key",))
        modified_at = self.file.modified_at

        move_fs_node(self.user, self.file.pk, self.other.pk)

        self.file.refresh_from_db()
        self.assertEqual(self.file.object_key, object_key)
        self.assertEqual(self.file.modified_at, modified_at)

    def test_move_keeps_active_share(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.file, owner=self.user)
        share_token = str(share.token)

        move_fs_node(self.user, self.file.pk, self.other.pk)

        share.refresh_from_db()
        self.assertEqual(str(share.token), share_token)
        self.assertEqual(share.root_fs_node_id, self.file.pk)

    def test_rejects_moving_into_itself(self) -> None:
        with self.assertRaises(FsNodeMoveError):
            move_fs_node(self.user, self.sub.pk, self.sub.pk)

    def test_rejects_moving_into_its_own_subtree(self) -> None:
        deep = FsNodeDirectoryFactory(
            name="deep",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

        with self.assertRaises(FsNodeMoveError):
            move_fs_node(self.user, self.sub.pk, deep.pk)

        self.assertEqual(
            FsNode.active.get(pk=self.sub.pk).parent_id,
            self.root.pk,
        )

    def test_rejects_moving_into_a_file(self) -> None:
        with self.assertRaises(FsNodeIsNotADirectoryError):
            move_fs_node(self.user, self.sub.pk, self.file.pk)

    def test_rejects_duplicate_name_in_destination(self) -> None:
        existing = FsNodeFileFactory(
            name="leaf.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.other,
        )

        with self.assertRaises(FsNodeExistsError) as ctx:
            move_fs_node(self.user, self.file.pk, self.other.pk)

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(existing.pk))
        self.assertEqual(ctx.exception.extra["existing_type"], FsNode.TypeChoices.FILE)

    def test_same_name_in_the_source_parent_does_not_block_move(self) -> None:
        moved = move_fs_node(self.user, self.file.pk, self.other.pk)

        self.assertEqual(moved.parent_id, self.other.pk)

    def test_rejects_foreign_node(self) -> None:
        other_user = UserFactory(storage=self.storage)
        foreign = FsNodeFileFactory(
            name="foreign.txt",
            owner=other_user,
            storage=self.storage,
            parent=self.other,
        )

        with self.assertRaises(FsNodeNotFoundError):
            move_fs_node(self.user, foreign.pk, self.sub.pk)

    def test_rejects_foreign_destination(self) -> None:
        other_user = UserFactory(storage=self.storage)
        foreign_dir = FsNodeDirectoryFactory(
            name="foreign-dir",
            owner=other_user,
            storage=self.storage,
            parent=self.other,
        )

        with self.assertRaises(FsNodeNotFoundError):
            move_fs_node(self.user, self.file.pk, foreign_dir.pk)

    def test_rejects_trashed_node(self) -> None:
        trash_fs_node(self.user, self.file.pk)

        with self.assertRaises(FsNodeNotFoundError):
            move_fs_node(self.user, self.file.pk, self.other.pk)

    def test_rejects_trashed_destination(self) -> None:
        trash_fs_node(self.user, self.other.pk)

        with self.assertRaises(FsNodeNotFoundError):
            move_fs_node(self.user, self.file.pk, self.other.pk)

    def test_rejects_cross_storage_destination(self) -> None:
        other_storage = FsStorage.objects.create(
            name="Other Storage",
            backend=self.storage.backend,
        )
        foreign_storage_dir = FsNodeDirectoryFactory(
            name="other-storage-dir",
            owner=self.user,
            storage=other_storage,
            parent=self.other,
        )

        with self.assertRaises(FsNodeMoveError):
            move_fs_node(self.user, self.file.pk, foreign_storage_dir.pk)

    def test_integrity_error_maps_to_conflict(self) -> None:
        existing = FsNodeFileFactory(
            name="leaf.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.other,
        )

        with (
            mock.patch.object(
                FsNode,
                "save",
                side_effect=IntegrityError("duplicate key"),
            ),
            mock.patch(
                "polyfile.apps.storage.utils._get_move_conflict",
                side_effect=[None, existing],
            ),
            self.assertRaises(FsNodeExistsError) as ctx,
        ):
            move_fs_node(self.user, self.file.pk, self.other.pk)

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(existing.pk))
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).parent_id,
            self.sub.pk,
        )


class MoveFsNodeApiTests(TestCase):
    """API tests for moving via `PATCH /api/v1/fs-node/<uuid:node_id>/`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.client.force_login(self.user)

        self.root = FsNodeDirectoryFactory(
            name="root",
            owner=self.user,
            storage=self.storage,
        )
        self.other = FsNodeDirectoryFactory(
            name="other",
            owner=self.user,
            storage=self.storage,
        )
        self.sub = FsNodeDirectoryFactory(
            name="sub",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        self.file = FsNodeFileFactory(
            name="leaf.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )
        self.deep = FsNodeDirectoryFactory(
            name="deep",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

        self.other_user = UserFactory(storage=self.storage)
        self.foreign = FsNodeDirectoryFactory(
            name="foreign",
            owner=self.other_user,
            storage=self.storage,
        )

    @staticmethod
    def _url(node_id: uuid.UUID) -> str:
        return reverse("fs_node_by_id", kwargs={"node_id": node_id})

    def _patch(self, node_id: uuid.UUID, body: dict | str):
        data = body if isinstance(body, str) else json.dumps(body)
        return self.client.patch(
            self._url(node_id),
            data=data,
            content_type="application/json",
        )

    def test_move_file_to_another_directory(self) -> None:
        response = self._patch(self.file.pk, {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["id"], str(self.file.pk))
        self.assertEqual(data["parent_id"], str(self.other.pk))
        self.assertEqual(data["name"], "leaf.txt")
        self.assertEqual(data["type"], FsNode.TypeChoices.FILE.value)
        self.assertTrue(
            FsNode.active.filter(pk=self.file.pk, parent=self.other).exists(),
        )

    def test_move_to_virtual_root(self) -> None:
        response = self._patch(self.file.pk, {"parent_id": None})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["parent_id"])
        self.assertIsNone(FsNode.active.get(pk=self.file.pk).parent_id)

    def test_move_updates_path_lookup(self) -> None:
        response = self._patch(self.file.pk, {"parent_id": str(self.other.pk)})
        self.assertEqual(response.status_code, 200, response.content)

        new_path = self.client.get(reverse("fs_node"), {"path": "/other/leaf.txt"})
        old_path = self.client.get(reverse("fs_node"), {"path": "/root/sub/leaf.txt"})

        self.assertEqual(new_path.status_code, 200)
        self.assertEqual(new_path.json()["current"]["name"], "leaf.txt")
        self.assertEqual(new_path.json()["current"]["parent_id"], str(self.other.pk))
        self.assertEqual(old_path.status_code, 404)

    def test_move_directory_with_children(self) -> None:
        response = self._patch(self.sub.pk, {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["parent_id"], str(self.other.pk))
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).parent_id,
            self.sub.pk,
        )
        nested = self.client.get(
            reverse("fs_node"),
            {"path": "/other/sub/leaf.txt"},
        )
        self.assertEqual(nested.status_code, 200)

    def test_move_into_itself_is_rejected(self) -> None:
        response = self._patch(self.sub.pk, {"parent_id": str(self.sub.pk)})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "FsNodeMoveError")

    def test_move_into_own_subtree_is_rejected(self) -> None:
        response = self._patch(self.sub.pk, {"parent_id": str(self.deep.pk)})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "FsNodeMoveError")
        self.assertEqual(
            FsNode.active.get(pk=self.sub.pk).parent_id,
            self.root.pk,
        )

    def test_move_into_a_file_is_rejected(self) -> None:
        response = self._patch(self.sub.pk, {"parent_id": str(self.file.pk)})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error_id"], "NotADirectoryError")

    def test_duplicate_name_reports_the_existing_node(self) -> None:
        existing = FsNodeFileFactory(
            name="leaf.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.other,
        )

        response = self._patch(self.file.pk, {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["error_id"], "FsNodeExistsError")
        self.assertEqual(data["existing_node_id"], str(existing.pk))
        self.assertEqual(data["existing_type"], FsNode.TypeChoices.FILE.value)

    def test_foreign_node_is_not_found(self) -> None:
        response = self._patch(self.foreign.pk, {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 404)
        self.assertTrue(FsNode.active.filter(pk=self.foreign.pk).exists())

    def test_foreign_destination_is_not_found(self) -> None:
        response = self._patch(self.file.pk, {"parent_id": str(self.foreign.pk)})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).parent_id,
            self.sub.pk,
        )

    def test_trashed_node_is_not_found(self) -> None:
        trash_fs_node(self.user, self.file.pk)

        response = self._patch(self.file.pk, {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 404)

    def test_unknown_node_is_not_found(self) -> None:
        response = self._patch(uuid.uuid4(), {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 404)

    def test_missing_update_fields_are_rejected(self) -> None:
        response = self._patch(self.file.pk, {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "FieldValidationError")

    def test_name_and_parent_id_together_are_rejected(self) -> None:
        response = self._patch(
            self.file.pk,
            {"name": "renamed.txt", "parent_id": str(self.other.pk)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "FieldValidationError")
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).parent_id,
            self.sub.pk,
        )

    def test_invalid_parent_id_is_rejected(self) -> None:
        response = self._patch(self.file.pk, {"parent_id": "not-a-uuid"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "FieldValidationError")

    def test_invalid_json_is_rejected(self) -> None:
        response = self._patch(self.file.pk, "{invalid")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "BadRequest")

    def test_unauthenticated_request_is_rejected(self) -> None:
        self.client.logout()

        response = self._patch(self.file.pk, {"parent_id": str(self.other.pk)})

        self.assertEqual(response.status_code, 401)
