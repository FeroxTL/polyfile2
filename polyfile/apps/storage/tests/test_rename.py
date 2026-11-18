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
from polyfile.apps.storage.models import FsNode
from polyfile.apps.storage.trash_service import trash_fs_node
from polyfile.apps.storage.utils import (
    remove_fs_node,
    rename_fs_node,
)
from polyfile.core.exceptions import (
    FsNodeExistsError,
    FsNodeNotFoundError,
    InvalidFsNodeName,
)


class RenameFsNodeTests(TestCase):
    """Unit tests for `rename_fs_node`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(
            name="root",
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

    def test_renames_file_in_place(self) -> None:
        renamed = rename_fs_node(self.user, self.file.pk, "renamed.txt")

        self.assertEqual(renamed.pk, self.file.pk)
        self.assertEqual(renamed.name, "renamed.txt")
        self.assertEqual(renamed.parent_id, self.sub.pk)
        self.assertEqual(renamed.type, FsNode.TypeChoices.FILE)
        self.assertEqual(
            FsNode.active.get(pk=self.file.pk).name,
            "renamed.txt",
        )

    def test_renames_directory_in_place(self) -> None:
        renamed = rename_fs_node(self.user, self.sub.pk, "renamed-sub")

        renamed.refresh_from_db()
        self.assertEqual(renamed.name, "renamed-sub")
        self.assertEqual(renamed.parent_id, self.root.pk)
        self.assertEqual(renamed.type, FsNode.TypeChoices.DIRECTORY)

    def test_renames_root_node(self) -> None:
        renamed = rename_fs_node(self.user, self.root.pk, "renamed-root")

        renamed.refresh_from_db()
        self.assertEqual(renamed.name, "renamed-root")
        self.assertIsNone(renamed.parent_id)

    def test_rename_keeps_object_key_and_modified_at(self) -> None:
        object_key = "2026/01/01/leaf.txt"
        self.file.object_key = object_key
        self.file.save(update_fields=("object_key",))
        modified_at = self.file.modified_at

        rename_fs_node(self.user, self.file.pk, "renamed.txt")

        self.file.refresh_from_db()
        self.assertEqual(self.file.object_key, object_key)
        self.assertEqual(self.file.modified_at, modified_at)

    def test_rename_keeps_active_share(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.file, owner=self.user)
        share_token = str(share.token)

        rename_fs_node(self.user, self.file.pk, "renamed.txt")

        share.refresh_from_db()
        self.assertEqual(str(share.token), share_token)
        self.assertEqual(share.root_fs_node_id, self.file.pk)

    def test_renaming_to_the_same_name_is_a_noop(self) -> None:
        with mock.patch.object(FsNode, "save") as save:
            renamed = rename_fs_node(self.user, self.file.pk, self.file.name)

        save.assert_not_called()
        self.assertEqual(renamed.pk, self.file.pk)
        self.assertEqual(renamed.name, "leaf.txt")

    def test_duplicate_sibling_name_is_rejected(self) -> None:
        existing = FsNodeFileFactory(
            name="taken.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

        with self.assertRaises(FsNodeExistsError) as ctx:
            rename_fs_node(self.user, self.file.pk, "taken.txt")

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(existing.pk))
        self.assertEqual(ctx.exception.extra["existing_type"], FsNode.TypeChoices.FILE)

    def test_duplicate_directory_name_is_rejected(self) -> None:
        existing = FsNodeDirectoryFactory(
            name="docs",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

        with self.assertRaises(FsNodeExistsError) as ctx:
            rename_fs_node(self.user, self.file.pk, "docs")

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(existing.pk))
        self.assertEqual(ctx.exception.extra["existing_type"], FsNode.TypeChoices.DIRECTORY)

    def test_duplicate_root_name_is_rejected(self) -> None:
        existing = FsNodeDirectoryFactory(
            name="other-root",
            owner=self.user,
            storage=self.storage,
        )

        with self.assertRaises(FsNodeExistsError) as ctx:
            rename_fs_node(self.user, self.root.pk, "other-root")

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(existing.pk))

    def test_same_name_in_a_different_parent_is_allowed(self) -> None:
        other_dir = FsNodeDirectoryFactory(
            name="other",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        FsNodeFileFactory(
            name="renamed.txt",
            owner=self.user,
            storage=self.storage,
            parent=other_dir,
        )

        renamed = rename_fs_node(self.user, self.file.pk, "renamed.txt")

        self.assertEqual(renamed.name, "renamed.txt")

    def test_trashed_sibling_name_does_not_block_rename(self) -> None:
        sibling = FsNodeFileFactory(
            name="trashed.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )
        trash_fs_node(self.user, sibling.pk)

        renamed = rename_fs_node(self.user, self.file.pk, "trashed.txt")

        self.assertEqual(renamed.name, "trashed.txt")

    def test_invalid_names_are_rejected(self) -> None:
        for name in ("", ".", "..", "a/b", "a\\b", "a<b", "a>b", "a:b", 'a"b', "a|b", "a?b", "a*b"):
            with self.assertRaises(InvalidFsNodeName, msg=f"name={name!r}"):
                rename_fs_node(self.user, self.file.pk, name)

    def test_too_long_name_is_rejected(self) -> None:
        with self.assertRaises(InvalidFsNodeName):
            rename_fs_node(self.user, self.file.pk, "a" * 256)

    def test_foreign_node_is_not_found(self) -> None:
        other_user = UserFactory(storage=self.storage)

        with self.assertRaises(FsNodeNotFoundError):
            rename_fs_node(other_user, self.file.pk, "renamed.txt")

    def test_trashed_node_is_not_found(self) -> None:
        trash_fs_node(self.user, self.file.pk)

        with self.assertRaises(FsNodeNotFoundError):
            rename_fs_node(self.user, self.file.pk, "renamed.txt")

    def test_tombstoned_node_is_not_found(self) -> None:
        remove_fs_node(self.user, self.file.pk)

        with self.assertRaises(FsNodeNotFoundError):
            rename_fs_node(self.user, self.file.pk, "renamed.txt")

    def test_unique_constraint_race_is_reported_as_conflict(self) -> None:
        conflict = FsNodeFileFactory(
            name="taken.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

        with (
            mock.patch(
                "polyfile.apps.storage.utils._get_active_sibling",
                return_value=conflict,
            ),
            mock.patch.object(
                FsNode,
                "save",
                side_effect=IntegrityError("duplicate key"),
            ),
            self.assertRaises(FsNodeExistsError) as ctx,
        ):
            rename_fs_node(self.user, self.file.pk, "taken.txt")

        self.assertEqual(ctx.exception.extra["existing_node_id"], str(conflict.pk))


class RenameFsNodeApiTests(TestCase):
    """API tests for `PATCH /api/v1/fs-node/<uuid:node_id>/`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.client.force_login(self.user)

        self.root = FsNodeDirectoryFactory(
            name="root",
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

    def test_rename_file(self) -> None:
        response = self._patch(self.file.pk, {"name": "renamed.txt"})

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["id"], str(self.file.pk))
        self.assertEqual(data["parent_id"], str(self.sub.pk))
        self.assertEqual(data["name"], "renamed.txt")
        self.assertEqual(data["type"], FsNode.TypeChoices.FILE.value)
        self.assertTrue(
            FsNode.active.filter(pk=self.file.pk, name="renamed.txt").exists(),
        )

    def test_rename_updates_path_lookup(self) -> None:
        response = self._patch(self.file.pk, {"name": "renamed.txt"})
        self.assertEqual(response.status_code, 200, response.content)

        new_path = self.client.get(reverse("fs_node"), {"path": "/root/sub/renamed.txt"})
        old_path = self.client.get(reverse("fs_node"), {"path": "/root/sub/leaf.txt"})

        self.assertEqual(new_path.status_code, 200)
        self.assertEqual(new_path.json()["current"]["name"], "renamed.txt")
        self.assertEqual(old_path.status_code, 404)

    def test_rename_directory(self) -> None:
        response = self._patch(self.sub.pk, {"name": "renamed-sub"})

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["name"], "renamed-sub")
        self.assertEqual(response.json()["parent_id"], str(self.root.pk))

    def test_rename_keeps_active_share(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.file, owner=self.user)

        response = self._patch(self.file.pk, {"name": "renamed.txt"})

        self.assertEqual(response.status_code, 200, response.content)
        share.refresh_from_db()
        self.assertEqual(share.root_fs_node_id, self.file.pk)

    def test_duplicate_name_reports_the_existing_node(self) -> None:
        existing = FsNodeFileFactory(
            name="taken.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.sub,
        )

        response = self._patch(self.file.pk, {"name": "taken.txt"})

        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertEqual(data["error_id"], "FsNodeExistsError")
        self.assertEqual(data["existing_node_id"], str(existing.pk))
        self.assertEqual(data["existing_type"], FsNode.TypeChoices.FILE.value)

    def test_foreign_node_is_not_found(self) -> None:
        response = self._patch(self.foreign.pk, {"name": "renamed"})
        self.assertEqual(response.status_code, 404)

    def test_trashed_node_is_not_found(self) -> None:
        trash_fs_node(self.user, self.file.pk)

        response = self._patch(self.file.pk, {"name": "renamed.txt"})
        self.assertEqual(response.status_code, 404)

    def test_tombstoned_node_is_not_found(self) -> None:
        remove_fs_node(self.user, self.file.pk)

        response = self._patch(self.file.pk, {"name": "renamed.txt"})
        self.assertEqual(response.status_code, 404)

    def test_unknown_node_is_not_found(self) -> None:
        response = self._patch(uuid.uuid4(), {"name": "renamed.txt"})
        self.assertEqual(response.status_code, 404)

    def test_missing_name_is_rejected(self) -> None:
        response = self._patch(self.file.pk, {})
        self.assertEqual(response.status_code, 400)

    def test_invalid_name_is_rejected(self) -> None:
        response = self._patch(self.file.pk, {"name": "a/b"})
        self.assertEqual(response.status_code, 400)

    def test_invalid_json_is_rejected(self) -> None:
        response = self._patch(self.file.pk, "{invalid")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error_id"], "BadRequest")

    def test_unauthenticated_request_is_rejected(self) -> None:
        self.client.logout()

        response = self._patch(self.file.pk, {"name": "renamed.txt"})
        self.assertEqual(response.status_code, 401)
