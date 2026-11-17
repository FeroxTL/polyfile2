"""Tests for trash TTL sweep: worker integration and the purge_expired_trash command."""

import io
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob
from polyfile.apps.storage.trash_service import (
    get_trash_roots,
    trash_fs_node,
)
from polyfile.apps.storage.utils import remove_fs_node


class TrashCommandTestCase(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(name="sub", owner=self.user, storage=self.storage, parent=self.root)
        self.file1 = FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)
        self.file2 = FsNodeFileFactory(name="f2.txt", owner=self.user, storage=self.storage, parent=self.sub)

    def _expire(self, entry: FsNode) -> None:
        FsNode.objects.filter(pk=entry.pk).update(trash_purge_after=now() - timedelta(minutes=1))


class PurgeExpiredTrashCommandTests(TrashCommandTestCase):
    def test_command_marks_expired_entries_for_deletion(self) -> None:
        expired = trash_fs_node(self.user, self.file1.pk)
        fresh = trash_fs_node(self.user, self.sub.pk)
        self._expire(expired)

        out = io.StringIO()
        call_command("purge_expired_trash", stdout=out)

        self.assertIn("Enqueued 1 trash purge job(s)", out.getvalue())
        self.assertIsNotNone(FsNode.objects.get(pk=expired.pk).deleted_at)
        self.assertIsNone(FsNode.objects.get(pk=fresh.pk).deleted_at)
        self.assertEqual(list(get_trash_roots(self.user).values_list("name", flat=True)), ["sub"])

    def test_command_does_nothing_without_expired_entries(self) -> None:
        trash_fs_node(self.user, self.file1.pk)

        out = io.StringIO()
        call_command("purge_expired_trash", stdout=out)

        self.assertIn("Enqueued 0 trash purge job(s)", out.getvalue())
        self.assertEqual(len(get_trash_roots(self.user)), 1)

    def test_command_protects_nested_entries(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        outer = trash_fs_node(self.user, self.root.pk)
        self._expire(outer)

        call_command("purge_expired_trash", stdout=io.StringIO())

        self.assertEqual(list(get_trash_roots(self.user).values_list("name", flat=True)), ["f2.txt"])

    def test_command_reaps_orphaned_scaffolding(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)
        self._expire(FsNode.trash.get(pk=self.file2.pk))

        # A single pass enqueues the purge and reaps what became childless
        # only after the worker removed tombstoned rows; run the command
        # twice to cover both stages.
        call_command("purge_expired_trash", stdout=io.StringIO())
        call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())
        call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())
        out = io.StringIO()
        call_command("purge_expired_trash", stdout=out)

        self.assertIn("Removed", out.getvalue())
        self.assertFalse(FsNode.objects.filter(pk=self.sub.pk).exists())

    def test_command_no_reap_flag_skips_scaffolding_cleanup(self) -> None:
        trash_fs_node(self.user, self.file2.pk)
        remove_fs_node(self.user, self.root.pk)
        self._expire(FsNode.trash.get(pk=self.file2.pk))
        call_command("purge_expired_trash", stdout=io.StringIO())
        call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())

        out = io.StringIO()
        call_command("purge_expired_trash", "--no-reap", stdout=out)

        self.assertNotIn("Removed", out.getvalue())
        self.assertTrue(FsNode.objects.filter(pk=self.sub.pk).exists())


class DeletionWorkerTrashSweepTests(TrashCommandTestCase):
    def test_worker_sweeps_expired_entries(self) -> None:
        expired = trash_fs_node(self.user, self.file1.pk)
        self._expire(expired)

        call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())

        entry = FsNode.objects.filter(pk=expired.pk).first()
        if entry is not None:
            # Either tombstoned, or already physically removed in this pass.
            self.assertIsNotNone(entry.deleted_at)
        self.assertEqual(list(get_trash_roots(self.user)), [])

    def test_worker_sweep_can_be_disabled(self) -> None:
        expired = trash_fs_node(self.user, self.file1.pk)
        self._expire(expired)

        call_command(
            "run_deletion_worker",
            "--once",
            "--trash-sweep-interval", "0",
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )

        self.assertIsNone(FsNode.objects.get(pk=expired.pk).deleted_at)

    def test_worker_processes_sweep_created_jobs(self) -> None:
        # Jobs created by the sweep must run to completion across passes.
        files = [
            FsNodeFileFactory(name=f"expired{i}.txt", owner=self.user, storage=self.storage, parent=self.root)
            for i in range(3)
        ]
        for file in files:
            self._expire(trash_fs_node(self.user, file.pk))

        for _ in range(4):
            call_command("run_deletion_worker", "--once", stdout=io.StringIO(), stderr=io.StringIO())

        for file in files:
            self.assertFalse(FsNode.objects.filter(pk=file.pk).exists())
        self.assertEqual(
            FsNodeDeletionJob.objects.filter(owner=self.user, status=FsNodeDeletionJob.Status.DONE).count(),
            3,
        )
