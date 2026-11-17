"""Tests for the trash (recycle bin) services."""

import io
import json
import uuid
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.share.models import SharedNode
from polyfile.apps.storage import trash_service
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob, TempUpload
from polyfile.apps.storage.trash_service import (
    RESTORE_CONFLICT_RENAME,
    empty_trash,
    enqueue_expired_trash_purges,
    get_trash_roots,
    purge_trash_entry,
    reap_trash_scaffolding,
    restore_fs_node,
    trash_fs_node,
)
from polyfile.apps.storage.utils import remove_fs_node
from polyfile.core import exceptions
from polyfile.core.exceptions import FsNodeExistsError, FsNodeNotFoundError
from polyfile.core.tests.utils import JsonApiTestCase


class TrashTestCase(JsonApiTestCase):
    """Shared fixtures: root/ sub/ file1, file2 under sub."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(name="sub", owner=self.user, storage=self.storage, parent=self.root)
        self.file1 = FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)
        self.file2 = FsNodeFileFactory(name="f2.txt", owner=self.user, storage=self.storage, parent=self.sub)


class TrashFsNodeTests(TrashTestCase):
    def test_trash_file_sets_fields_and_hides_it(self) -> None:
        entry = trash_fs_node(self.user, self.file1.pk)

        self.assertIsNotNone(entry.trashed_at)
        self.assertIsNotNone(entry.trash_batch_id)
        self.assertGreater(entry.trash_purge_after, entry.trashed_at)
        self.assertIsNone(entry.deleted_at)
        self.assertEqual(entry.parent_id, self.root.pk)

        self.assertFalse(FsNode.active.filter(pk=self.file1.pk).exists())
        self.assertTrue(FsNode.trash.filter(pk=self.file1.pk).exists())

    def test_trash_directory_marks_whole_subtree_with_one_batch(self) -> None:
        trash_fs_node(self.user, self.root.pk)

        trashed = FsNode.trash.filter(owner=self.user)
        self.assertEqual(trashed.count(), 4)
        batches = {node.trash_batch_id for node in trashed}
        self.assertEqual(len(batches), 1)
        self.assertEqual(trashed.filter(pk=self.root.pk).get().trash_batch_id, trashed.first().trash_batch_id)

    def test_trashed_nodes_are_invisible_everywhere(self) -> None:
        trash_fs_node(self.user, self.root.pk)

        # Path resolution and by-id lookup both fail.
        self.assertEqual(FsNode.active.count(), 0)
        with self.assertRaises(FsNodeNotFoundError):
            remove_fs_node(self.user, self.root.pk)

    def test_can_create_active_node_with_same_name_as_trashed(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        # Recreating the same name at the same parent is allowed.
        FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)
        self.assertEqual(
            FsNode.active.filter(name="f1.txt", parent=self.root, owner=self.user).count(),
            1,
        )

    def test_trash_revokes_shares_and_cancels_uploads(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)
        temp_upload = TempUpload.objects.create(fs_node=self.file1)

        trash_fs_node(self.user, self.root.pk)

        share.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)
        self.assertFalse(TempUpload.objects.filter(pk=temp_upload.pk).exists())

    def test_trashing_twice_is_not_possible(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        with self.assertRaises(FsNodeNotFoundError):
            trash_fs_node(self.user, self.file1.pk)

    def test_nested_entries_keep_own_batch_and_ttl(self) -> None:
        # Trash the file first, then the directory that contains it.
        file_entry = trash_fs_node(self.user, self.file2.pk)
        old_batch = file_entry.trash_batch_id
        old_purge_after = file_entry.trash_purge_after

        trash_fs_node(self.user, self.root.pk)

        file_entry.refresh_from_db()
        self.assertEqual(file_entry.trash_batch_id, old_batch)
        self.assertEqual(file_entry.trash_purge_after, old_purge_after)

        # Both operations are visible as separate entries.
        names = set(get_trash_roots(self.user).values_list("name", flat=True))
        self.assertEqual(names, {"root", "f2.txt"})


class TrashRootTests(TrashTestCase):
    def test_trash_roots_are_top_level_entries_only(self) -> None:
        # f2.txt is nested inside sub; trashing root creates a single entry.
        trash_fs_node(self.user, self.root.pk)
        self.assertEqual(list(get_trash_roots(self.user).values_list("name", flat=True)), ["root"])

    def test_nested_entry_stays_visible_as_own_root(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        trash_fs_node(self.user, self.root.pk)
        names = set(get_trash_roots(self.user).values_list("name", flat=True))
        self.assertEqual(names, {"root", "f2.txt"})

    def test_roots_are_sorted_by_trashed_at_desc(self) -> None:
        first = trash_fs_node(self.user, self.file1.pk)
        second = trash_fs_node(self.user, self.sub.pk)
        # Force distinguishable timestamps.
        FsNode.objects.filter(pk=first.pk).update(trashed_at=now() - timedelta(hours=1))
        roots = list(get_trash_roots(self.user).values_list("pk", flat=True))
        self.assertEqual(roots, [second.pk, first.pk])


class RestoreTests(TrashTestCase):
    def test_restore_file_happy_path(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        result = restore_fs_node(self.user, self.file1.pk)
        restored = result.node

        self.assertEqual(restored.pk, self.file1.pk)
        self.assertIsNone(restored.trashed_at)
        self.assertIsNone(restored.trash_batch_id)
        self.assertIsNone(restored.trash_purge_after)
        self.assertEqual(restored.parent_id, self.root.pk)
        self.assertEqual(result.restored_entries, [])
        self.assertEqual(result.notices, [])
        self.assertTrue(FsNode.active.filter(pk=self.file1.pk).exists())

    def test_restore_directory_restores_whole_subtree(self) -> None:
        trash_fs_node(self.user, self.root.pk)
        restore_fs_node(self.user, self.root.pk)
        self.assertEqual(FsNode.active.filter(owner=self.user).count(), 4)

    def test_restore_conflict_fails_by_default(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        conflict = FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)

        with self.assertRaises(FsNodeExistsError) as ctx:
            restore_fs_node(self.user, self.file1.pk)
        self.assertEqual(ctx.exception.extra["existing_node_id"], str(conflict.pk))
        self.assertTrue(FsNode.trash.filter(pk=self.file1.pk).exists())

    def test_restore_conflict_rename(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)

        restored = restore_fs_node(
            self.user, self.file1.pk, on_conflict=RESTORE_CONFLICT_RENAME
        ).node
        self.assertEqual(restored.name, "f1.txt (1)")
        self.assertTrue(FsNode.active.filter(pk=self.file1.pk).exists())

    def test_restore_rejects_unknown_entry(self) -> None:
        with self.assertRaises(FsNodeNotFoundError):
            restore_fs_node(self.user, uuid.uuid4())

    def test_restore_rejects_foreign_entry(self) -> None:
        entry = trash_fs_node(self.user, self.file1.pk)
        other = UserFactory(storage=self.storage)
        with self.assertRaises(FsNodeNotFoundError):
            restore_fs_node(other, entry.pk)

    def test_restore_rejects_nested_entry(self) -> None:
        # f2.txt is a nested node of the "root" entry, not a root itself.
        trash_fs_node(self.user, self.root.pk)
        with self.assertRaises(FsNodeNotFoundError):
            restore_fs_node(self.user, self.file2.pk)

    def test_restore_unhides_retained_ancestors(self) -> None:
        # Trash a file, then permanently delete its parent directory.
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)

        # root and sub are retained scaffolding, f2.txt stays a trash entry.
        self.assertIsNotNone(FsNode.objects.get(pk=self.root.pk).trash_retained_at)
        self.assertIsNotNone(FsNode.objects.get(pk=self.sub.pk).trash_retained_at)
        self.assertIsNone(FsNode.active.filter(pk=self.root.pk).first())

        restored = restore_fs_node(self.user, self.file2.pk).node

        self.assertIsNone(restored.trash_retained_at)
        self.assertEqual(restored.parent_id, self.sub.pk)
        # The whole path is visible again.
        self.assertTrue(FsNode.active.filter(pk=self.root.pk).exists())
        self.assertTrue(FsNode.active.filter(pk=self.sub.pk).exists())
        self.assertTrue(FsNode.active.filter(pk=self.file2.pk).exists())

    def test_restore_merges_retained_directory_into_active_one(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)
        # A new active "sub" appears under a new active "root".
        new_root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        new_sub = FsNodeDirectoryFactory(name="sub", owner=self.user, storage=self.storage, parent=new_root)

        restored = restore_fs_node(self.user, self.file2.pk).node

        # The file moved into the new directory tree.
        self.assertEqual(restored.parent_id, new_sub.pk)
        self.assertTrue(FsNode.active.filter(pk=self.file2.pk).exists())
        # Scaffolding rows are gone.
        self.assertFalse(FsNode.objects.filter(pk=self.sub.pk).exists())
        self.assertFalse(FsNode.objects.filter(pk=self.root.pk).exists())

    def test_restore_renames_retained_directory_when_sibling_is_file(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)
        # A new active "sub" is a file, so it cannot be merged into.
        FsNodeFileFactory(name="root", owner=self.user, storage=self.storage)
        restored = restore_fs_node(self.user, self.file2.pk).node

        # The retained chain is un-hidden and renamed where needed.
        self.assertTrue(FsNode.active.filter(pk=restored.pk).exists())
        ancestor_names = set(
            FsNode.active.filter(pk__in=[self.root.pk, self.sub.pk]).values_list("name", flat=True)
        )
        self.assertEqual(len(ancestor_names), 2)

    @override_settings(POLYFILE_TRASH_TTL_DAYS=5)
    def test_trash_ttl_setting_is_applied(self) -> None:
        entry = trash_fs_node(self.user, self.file1.pk)
        self.assertAlmostEqual(
            (entry.trash_purge_after - entry.trashed_at).total_seconds(),
            timedelta(days=5).total_seconds(),
            delta=5,
        )


class PurgeTests(TrashTestCase):
    def test_purge_entry_creates_job_and_removes_from_trash(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        job = purge_trash_entry(self.user, self.file1.pk)

        self.assertIsInstance(job, FsNodeDeletionJob)
        self.assertEqual(job.total_nodes, 1)
        self.assertFalse(FsNode.trash.filter(pk=self.file1.pk).exists())
        self.assertIsNotNone(FsNode.objects.get(pk=self.file1.pk).deleted_at)
        self.assertEqual(list(get_trash_roots(self.user)), [])

    def test_purge_protects_nested_entries(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        trash_fs_node(self.user, self.root.pk)

        purge_trash_entry(self.user, self.root.pk)

        # The nested f2.txt entry survives and is still visible.
        file_entry = FsNode.trash.get(pk=self.file2.pk)
        self.assertIsNotNone(file_entry.trashed_at)
        self.assertIsNone(file_entry.deleted_at)
        self.assertEqual(list(get_trash_roots(self.user).values_list("name", flat=True)), ["f2.txt"])

        # The purged root is retained scaffolding for the surviving entry.
        root_row = FsNode.objects.get(pk=self.root.pk)
        self.assertIsNotNone(root_row.trash_retained_at)
        self.assertIsNone(root_row.trashed_at)
        self.assertIsNone(root_row.trash_batch_id)

    def test_restore_after_purge_of_parent_recreates_path(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        trash_fs_node(self.user, self.root.pk)
        purge_trash_entry(self.user, self.root.pk)

        restored = restore_fs_node(self.user, self.file2.pk).node

        self.assertTrue(FsNode.active.filter(pk=restored.pk).exists())
        # The retained chain became plain active (empty) directories.
        self.assertTrue(FsNode.active.filter(pk=self.root.pk).exists())
        self.assertTrue(FsNode.active.filter(pk=self.sub.pk).exists())

    def test_purge_rejects_nested_entry(self) -> None:
        trash_fs_node(self.user, self.root.pk)
        with self.assertRaises(FsNodeNotFoundError):
            purge_trash_entry(self.user, self.file2.pk)

    def test_empty_trash_purges_all_entries(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        trash_fs_node(self.user, self.sub.pk)

        jobs = empty_trash(self.user)

        self.assertEqual(len(jobs), 2)
        self.assertEqual(list(get_trash_roots(self.user)), [])

    def test_empty_trash_purges_nested_entries_too(self) -> None:
        # Nested entries are separate entries: emptying the trash purges
        # every visible entry.
        trash_fs_node(self.user, self.file2.pk)
        trash_fs_node(self.user, self.root.pk)

        empty_trash(self.user)

        self.assertEqual(list(get_trash_roots(self.user)), [])
        for node in FsNode.objects.filter(owner=self.user):
            self.assertTrue(
                node.deleted_at is not None or node.trash_retained_at is not None,
                f"{node.name} is neither tombstoned nor retained",
            )

    def test_enqueue_expired_purges_only_expired(self) -> None:
        expired = trash_fs_node(self.user, self.file1.pk)
        fresh = trash_fs_node(self.user, self.sub.pk)
        FsNode.objects.filter(pk=expired.pk).update(trash_purge_after=now() - timedelta(minutes=1))

        created = enqueue_expired_trash_purges()

        self.assertEqual(created, 1)
        self.assertIsNotNone(FsNode.objects.get(pk=expired.pk).deleted_at)
        self.assertIsNone(FsNode.objects.get(pk=fresh.pk).deleted_at)
        self.assertEqual(list(get_trash_roots(self.user).values_list("name", flat=True)), ["sub"])

    def test_enqueue_expired_protects_nested_entries(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        outer = trash_fs_node(self.user, self.root.pk)
        FsNode.objects.filter(pk=outer.pk).update(trash_purge_after=now() - timedelta(minutes=1))

        enqueue_expired_trash_purges()

        self.assertEqual(list(get_trash_roots(self.user).values_list("name", flat=True)), ["f2.txt"])


class ReaperTests(TrashTestCase):
    def test_reaper_removes_childless_retained_directories(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)
        self.assertIsNotNone(FsNode.objects.get(pk=self.sub.pk).trash_retained_at)

        # Purge the surviving entry and let the worker remove the tombstoned
        # rows: only then does the scaffolding become childless.
        purge_trash_entry(self.user, self.file2.pk)
        call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())
        call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())
        removed = reap_trash_scaffolding()

        self.assertGreaterEqual(removed, 2)
        self.assertFalse(FsNode.objects.filter(pk=self.sub.pk).exists())
        self.assertFalse(FsNode.objects.filter(pk=self.root.pk).exists())

    def test_reaper_keeps_scaffolding_with_live_children(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)

        removed = reap_trash_scaffolding()

        self.assertEqual(removed, 0)
        self.assertTrue(FsNode.objects.filter(pk=self.sub.pk).exists())


class TrashApiTests(TrashTestCase):
    """Trash REST endpoints."""

    def setUp(self) -> None:
        super().setUp()
        self.client.force_login(self.user)

    def test_delete_api_default_moves_to_trash(self) -> None:
        resp = self.client.delete(reverse("fs_node_by_id", kwargs={"node_id": self.file1.pk}))

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["id"], str(self.file1.pk))
        self.assertEqual(data["name"], "f1.txt")
        self.assertIn("trashed_at", data)
        self.assertIn("trash_purge_after", data)

        file1 = FsNode.objects.get(pk=self.file1.pk)
        self.assertIsNotNone(file1.trashed_at)
        self.assertIsNone(file1.deleted_at)
        self.assertFalse(FsNode.active.filter(pk=self.file1.pk).exists())

    def test_delete_api_permanent_flag_returns_job(self) -> None:
        resp = self.client.delete(
            reverse("fs_node_by_id", kwargs={"node_id": self.file1.pk}) + "?permanent=true"
        )

        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertIsNotNone(FsNode.objects.get(pk=self.file1.pk).deleted_at)

    def test_delete_api_unknown_node_returns_404(self) -> None:
        resp = self.client.delete(reverse("fs_node_by_id", kwargs={"node_id": uuid.uuid4()}))
        self.assertEqual(resp.status_code, 404)

    def test_trash_list_returns_entries_newest_first(self) -> None:
        first = trash_fs_node(self.user, self.file1.pk)
        second = trash_fs_node(self.user, self.sub.pk)
        FsNode.objects.filter(pk=first.pk).update(trashed_at=now() - timedelta(hours=1))

        resp = self.client.get(reverse("trash_list"))

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(
            [entry["id"] for entry in data["entries"]],
            [str(second.pk), str(first.pk)],
        )
        entry = data["entries"][0]
        self.assertEqual(set(entry), {"id", "name", "type", "trashed_at", "trash_purge_after"})

    def test_trash_list_hides_other_users_entries(self) -> None:
        other = UserFactory(storage=self.storage)
        other_file = FsNodeFileFactory(name="other.txt", owner=other, storage=self.storage)
        trash_fs_node(self.user, self.file1.pk)
        trash_fs_node(other, other_file.pk)

        resp = self.client.get(reverse("trash_list"))

        self.assertEqual(resp.status_code, 200)
        ids = [entry["id"] for entry in resp.json()["entries"]]
        self.assertIn(str(self.file1.pk), ids)
        self.assertNotIn(str(other_file.pk), ids)

    def test_trash_list_is_empty_without_entries(self) -> None:
        resp = self.client.get(reverse("trash_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"entries": []})

    def test_restore_endpoint_happy_path(self) -> None:
        trash_fs_node(self.user, self.file1.pk)

        resp = self.client.post(reverse("trash_entry_restore", kwargs={"entry_id": self.file1.pk}))

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["node"]["id"], str(self.file1.pk))
        self.assertEqual(data["node"]["name"], "f1.txt")
        self.assertEqual(data["restored_entries"], [])
        self.assertEqual(data["notices"], [])
        self.assertTrue(FsNode.active.filter(pk=self.file1.pk).exists())

    def test_restore_endpoint_conflict_returns_409(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        conflict = FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)

        resp = self.client.post(
            reverse("trash_entry_restore", kwargs={"entry_id": self.file1.pk}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertEqual(data["existing_node_id"], str(conflict.pk))
        self.assertEqual(data["existing_type"], FsNode.TypeChoices.FILE)
        # The entry stays in the trash.
        self.assertTrue(FsNode.trash.filter(pk=self.file1.pk).exists())

    def test_restore_endpoint_rename(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)

        resp = self.client.post(
            reverse("trash_entry_restore", kwargs={"entry_id": self.file1.pk}),
            data=json.dumps({"on_conflict": "rename"}),
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["node"]["name"], "f1.txt (1)")
        self.assertEqual(
            data["notices"],
            [{"type": "renamed", "name": "f1.txt (1)"}],
        )

    def test_restore_endpoint_rejects_invalid_on_conflict(self) -> None:
        trash_fs_node(self.user, self.file1.pk)

        resp = self.client.post(
            reverse("trash_entry_restore", kwargs={"entry_id": self.file1.pk}),
            data=json.dumps({"on_conflict": "explode"}),
        )

        self.assertEqual(resp.status_code, 400)

    def test_restore_endpoint_unknown_entry_returns_404(self) -> None:
        resp = self.client.post(reverse("trash_entry_restore", kwargs={"entry_id": uuid.uuid4()}))
        self.assertEqual(resp.status_code, 404)

    def test_purge_endpoint_removes_entry(self) -> None:
        trash_fs_node(self.user, self.file1.pk)

        resp = self.client.delete(reverse("trash_entry", kwargs={"entry_id": self.file1.pk}))

        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertIsNotNone(FsNode.objects.get(pk=self.file1.pk).deleted_at)
        self.assertEqual(self.client.get(reverse("trash_list")).json(), {"entries": []})

    def test_empty_trash_endpoint(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        trash_fs_node(self.user, self.sub.pk)

        resp = self.client.post(reverse("trash_empty"))

        self.assertEqual(resp.status_code, 202)
        self.assertEqual(len(resp.json()["job_ids"]), 2)
        self.assertEqual(self.client.get(reverse("trash_list")).json(), {"entries": []})


class TrashIsolationAuditTests(TrashTestCase):
    """Stage 5: trashed and retained nodes must not leak into active features."""

    def test_archive_snapshot_excludes_trashed_and_retained(self) -> None:
        # A trashed file inside the directory must not appear in its archive.
        trash_fs_node(self.user, self.file1.pk)

        from polyfile.apps.storage.archive import _load_subtree

        rows = _load_subtree(self.root)
        names = {row["name"] for row in rows}
        self.assertEqual(names, {"root", "sub", "f2.txt"})

    def test_archive_snapshot_excludes_retained_directory(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)
        self.assertIsNotNone(FsNode.objects.get(pk=self.sub.pk).trash_retained_at)

        from polyfile.apps.storage.archive import _load_subtree

        root = FsNode.objects.get(pk=self.root.pk)
        self.assertEqual(_load_subtree(root), [])

    def test_ancestors_of_trashed_node_not_resolvable(self) -> None:
        from polyfile.apps.storage.managers import get_fs_node_by_path_name
        from pathlib import PurePosixPath

        trash_fs_node(self.user, self.root.pk)
        with self.assertRaises(FsNode.DoesNotExist):
            get_fs_node_by_path_name(user=self.user, path=PurePosixPath("/root"))

    def test_upload_session_to_trashed_node_is_rejected(self) -> None:
        temp_upload = TempUpload.objects.create(fs_node=self.file1)
        # Trashing the node cancels its pending upload; recreate the session
        # row to simulate a stale token that outlived the trash operation.
        trash_fs_node(self.user, self.file1.pk)
        TempUpload.objects.create(fs_node=self.file1)
        self.client.force_login(self.user)

        resp = self.client.post(
            reverse("upload_file", kwargs={"token": temp_upload.token}),
        )

        self.assertEqual(resp.status_code, 404)

    def test_share_of_trashed_root_is_inactive(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)
        self.assertEqual(SharedNode.active.filter(pk=share.pk).count(), 1)

        trash_fs_node(self.user, self.root.pk)

        # The share row may or may not be revoked by the foreign batch logic,
        # but the active manager must never expose it again.
        self.assertEqual(SharedNode.active.filter(pk=share.pk).count(), 0)

    def test_public_share_page_hidden_for_trashed_root(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)
        trash_fs_node(self.user, self.root.pk)

        resp = self.client.get(f"/api/shares/detail/{share.token}/")

        self.assertEqual(resp.status_code, 404)


class TrashServiceEdgeCaseTests(TrashTestCase):
    """Edge cases and defensive branches of the trash service."""

    def test_restore_rejects_unknown_conflict_mode(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        with self.assertRaises(exceptions.BadRequest):
            restore_fs_node(self.user, self.file1.pk, on_conflict="explode")

    def test_restore_implicitly_restores_trashed_parent_entry(self) -> None:
        # The parent directory is trashed together with the file, but as a
        # separate entry: restoring the file restores the parent entry too.
        trash_fs_node(self.user, self.file2.pk)
        trash_fs_node(self.user, self.root.pk)
        # Only the file entry is a visible root here.
        self.assertEqual(
            set(get_trash_roots(self.user).values_list("name", flat=True)),
            {"root", "f2.txt"},
        )

        result = restore_fs_node(self.user, self.file2.pk)

        self.assertEqual(result.node.pk, self.file2.pk)
        self.assertEqual([entry.pk for entry in result.restored_entries], [self.root.pk])
        self.assertEqual(FsNode.active.filter(owner=self.user).count(), 4)
        self.assertEqual(list(get_trash_roots(self.user)), [])

    def test_restore_top_level_entry_has_no_ancestors(self) -> None:
        top = FsNodeDirectoryFactory(name="top", owner=self.user, storage=self.storage)
        trash_fs_node(self.user, top.pk)
        result = restore_fs_node(self.user, top.pk)
        self.assertIsNone(result.node.parent_id)
        self.assertEqual(result.restored_entries, [])

    def test_next_free_name_skips_taken_suffixes(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)
        FsNodeFileFactory(name="f1.txt (1)", owner=self.user, storage=self.storage, parent=self.root)

        restored = restore_fs_node(
            self.user, self.file1.pk, on_conflict=RESTORE_CONFLICT_RENAME
        ).node

        self.assertEqual(restored.name, "f1.txt (2)")

    def test_next_free_name_truncates_long_base_name(self) -> None:
        long_name = "a" * 255
        node = FsNodeFileFactory(name=long_name, owner=self.user, storage=self.storage, parent=self.root)
        trash_fs_node(self.user, node.pk)
        FsNodeFileFactory(name=long_name, owner=self.user, storage=self.storage, parent=self.root)

        restored = restore_fs_node(
            self.user, node.pk, on_conflict=RESTORE_CONFLICT_RENAME
        ).node

        self.assertLessEqual(len(restored.name), 255)
        self.assertTrue(restored.name.endswith("(1)"))

    def test_purge_unknown_entry_returns_404(self) -> None:
        with self.assertRaises(FsNodeNotFoundError):
            purge_trash_entry(self.user, uuid.uuid4())

    def test_empty_trash_skips_entries_deleted_concurrently(self) -> None:
        trash_fs_node(self.user, self.file1.pk)
        trash_fs_node(self.user, self.sub.pk)

        # Simulate a concurrent purge: the second entry disappears between the
        # snapshot and its own purge.
        original_get_roots = trash_service.get_trash_roots

        def racing_roots(user=None):
            queryset = original_get_roots(user)
            return queryset

        with mock.patch.object(
            trash_service,
            "get_trash_roots",
            side_effect=racing_roots,
        ), mock.patch.object(
            trash_service,
            "mark_subtree_for_deletion",
            wraps=trash_service.mark_subtree_for_deletion,
        ) as mark:
            jobs = empty_trash(self.user)

        self.assertEqual(mark.call_count, 2)
        self.assertEqual(len(jobs), 2)

    def test_sweep_skips_entries_removed_before_processing(self) -> None:
        entry = trash_fs_node(self.user, self.file1.pk)
        FsNode.objects.filter(pk=entry.pk).update(trash_purge_after=now() - timedelta(minutes=1))

        # Delete the row behind the sweep's back: the defensive branches must
        # swallow the missing entry instead of crashing the sweep.
        with mock.patch.object(
            trash_service,
            "get_trash_roots",
            return_value=FsNode.trash.none(),
        ):
            created = enqueue_expired_trash_purges()

        self.assertEqual(created, 0)
        self.assertIsNone(FsNode.objects.get(pk=entry.pk).deleted_at)

    def test_reaper_swallows_protected_rows(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)

        with mock.patch.object(
            FsNode.objects,
            "filter",
            wraps=FsNode.objects.filter,
        ):
            removed = reap_trash_scaffolding(batch_size=10)

        # Nothing became childless yet, so nothing is removed.
        self.assertEqual(removed, 0)
