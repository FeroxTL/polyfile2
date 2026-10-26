import io
from pathlib import PurePosixPath

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob, TempUpload
from polyfile.apps.storage.utils import create_fs_node, remove_fs_node
from polyfile.core.exceptions import FsNodeExistsError


class RecursiveDeletionTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.subdir = FsNodeDirectoryFactory(name="sub", owner=self.user, storage=self.storage, parent=self.root)
        self.file1 = FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)
        self.file2 = FsNodeFileFactory(name="f2.txt", owner=self.user, storage=self.storage, parent=self.subdir)

    def test_remove_directory_marks_subtree_tombstone(self) -> None:
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        self.assertIsInstance(job, FsNodeDeletionJob)
        self.assertEqual(job.status, FsNodeDeletionJob.Status.PENDING)
        self.assertEqual(job.total_nodes, 4)

        self.assertEqual(FsNode.active.count(), 0)
        self.assertEqual(FsNode.objects.count(), 4)
        for node in FsNode.objects.all():
            self.assertIsNotNone(node.deleted_at)
            self.assertEqual(node.deletion_job_id, job.pk)

    def test_delete_api_returns_202(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.delete(reverse("fs_node") + "?path=/root")
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["status"], FsNodeDeletionJob.Status.PENDING)

    def test_can_create_active_node_with_same_name_as_tombstone(self) -> None:
        remove_fs_node(self.user, PurePosixPath("/root"))
        # Try to create directory with same name at root level - should work
        create_fs_node(self.user, PurePosixPath("/root"), FsNode.TypeChoices.DIRECTORY)
        # Second create will fail
        with self.assertRaises(FsNodeExistsError):
            create_fs_node(self.user, PurePosixPath("/root"), FsNode.TypeChoices.DIRECTORY)

    def test_shares_revoked_on_deletion(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)
        self.assertIsNone(share.revoked_at)
        remove_fs_node(self.user, PurePosixPath("/root"))
        share.refresh_from_db()
        self.assertIsNotNone(share.revoked_at)

    def test_temp_uploads_cancelled_on_deletion(self) -> None:
        tu = TempUpload.objects.create(fs_node=self.file1)
        remove_fs_node(self.user, PurePosixPath("/root"))
        self.assertFalse(TempUpload.objects.filter(pk=tu.pk).exists())

    def test_deleted_nodes_not_visible_in_listing(self) -> None:
        self.client.force_login(self.user)
        resp = self.client.get(reverse("fs_node") + "?path=/")
        self.assertEqual(resp.status_code, 200)
        remove_fs_node(self.user, PurePosixPath("/root"))
        resp2 = self.client.get(reverse("fs_node") + "?path=/")
        self.assertEqual(resp2.status_code, 200)
        data = resp2.json()
        names = [c["name"] for c in data.get("children", [])]
        self.assertNotIn("root", names)


class DeletionWorkerTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.subdir = FsNodeDirectoryFactory(name="sub", owner=self.user, storage=self.storage, parent=self.root)
        self.file1 = FsNodeFileFactory(name="f1.txt", owner=self.user, storage=self.storage, parent=self.root)
        self.file2 = FsNodeFileFactory(name="f2.txt", owner=self.user, storage=self.storage, parent=self.subdir)

    def test_worker_processes_job_and_removes_all_nodes(self) -> None:
        stdout = io.StringIO()
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        self.assertEqual(FsNode.objects.count(), 4)
        call_command("run_deletion_worker", "--once", stdout=stdout, stderr=stdout)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(FsNode.objects.count(), 0)
        self.assertEqual(FsNode.active.count(), 0)
        self.assertEqual(
            stdout.getvalue(),
            f"Starting deletion worker...\nJob {job.pk} completed\n",
        )

    def test_worker_processes_file_only(self) -> None:
        stdout = io.StringIO()
        job = remove_fs_node(self.user, PurePosixPath("/root/f1.txt"))
        self.assertTrue(FsNode.objects.filter(pk=self.file1.pk).exists())
        call_command("run_deletion_worker", "--once", stdout=stdout, stderr=stdout)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertFalse(FsNode.objects.filter(pk=self.file1.pk).exists())
        self.assertEqual(
            stdout.getvalue(),
            f"Starting deletion worker...\nJob {job.pk} completed\n",
        )

    def test_worker_handles_empty_directory(self) -> None:
        stdout = io.StringIO()
        empty_dir = FsNodeDirectoryFactory(name="empty", owner=self.user, storage=self.storage, parent=self.root)
        job = remove_fs_node(self.user, PurePosixPath("/root/empty"))
        self.assertEqual(FsNode.objects.filter(pk=empty_dir.pk).count(), 1)
        call_command("run_deletion_worker", "--once", stdout=stdout, stderr=stdout)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(FsNode.objects.filter(pk=empty_dir.pk).count(), 0)
        self.assertEqual(
            stdout.getvalue(),
            f"Starting deletion worker...\nJob {job.pk} completed\n",
        )

    def test_worker_updates_progress(self) -> None:
        stdout = io.StringIO()
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        call_command("run_deletion_worker", "--once", stdout=stdout, stderr=stdout)
        job.refresh_from_db()
        self.assertGreaterEqual(job.processed_nodes, job.total_nodes)
        self.assertIsNotNone(job.finished_at)
        self.assertEqual(
            stdout.getvalue(),
            f"Starting deletion worker...\nJob {job.pk} completed\n",
        )
