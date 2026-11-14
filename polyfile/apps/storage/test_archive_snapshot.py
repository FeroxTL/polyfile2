from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.share.services import revoke_public_share
from polyfile.apps.storage.archive import create_archive_job
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import (
    FsNode,
    FsNodeArchiveItem,
    FsNodeArchiveJob,
)
from polyfile.apps.storage.storage_objects import StorageObjectRef
from polyfile.apps.storage.utils import remove_fs_node
from polyfile.core import exceptions


class ArchiveSnapshotTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(
            name="root",
            owner=self.user,
            storage=self.storage,
        )
        self.subdir = FsNodeDirectoryFactory(
            name="sub",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        self.empty_dir = FsNodeDirectoryFactory(
            name="empty",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        self.file1 = FsNodeFileFactory(
            name="a.txt",
            object_key="uploads/a/a.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=10,
            md5="a" * 32,
        )
        self.file2 = FsNodeFileFactory(
            name="b.txt",
            object_key="uploads/b/b.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.subdir,
            size=20,
            md5="b" * 32,
        )

    def _items(self, job: FsNodeArchiveJob) -> list[FsNodeArchiveItem]:
        return list(job.items.order_by("position"))

    def test_manifest_contains_nested_files_and_empty_directories(self) -> None:
        job = create_archive_job(self.user, self.root)

        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)
        self.assertEqual(job.root_node_uuid, self.root.pk)
        self.assertEqual(job.root_node_name, "root")
        self.assertEqual(job.requested_by, self.user)
        self.assertEqual(job.total_files, 2)
        self.assertEqual(job.total_bytes, 30)

        items = self._items(job)
        self.assertEqual(
            [item.zip_path for item in items],
            ["a.txt", "empty/", "sub/", "sub/b.txt"],
        )
        self.assertEqual([item.position for item in items], [0, 1, 2, 3])

        by_path = {item.zip_path: item for item in items}
        self.assertEqual(by_path["a.txt"].node_id, self.file1.pk)
        self.assertEqual(by_path["a.txt"].entry_type, FsNodeArchiveItem.EntryType.FILE)
        self.assertEqual(by_path["a.txt"].object_key, "uploads/a/a.txt")
        self.assertEqual(by_path["a.txt"].storage_id, self.storage.pk)
        self.assertEqual(
            by_path["a.txt"].storage_object,
            StorageObjectRef(self.storage.pk, "uploads/a/a.txt"),
        )
        self.assertEqual(by_path["a.txt"].size, 10)
        self.assertEqual(by_path["a.txt"].md5, "a" * 32)

        self.assertEqual(
            by_path["empty/"].entry_type,
            FsNodeArchiveItem.EntryType.DIRECTORY,
        )
        self.assertIsNone(by_path["empty/"].node_id)
        self.assertIsNone(by_path["empty/"].storage_id)
        self.assertEqual(by_path["empty/"].object_key, "")
        self.assertIsNone(by_path["empty/"].storage_object)

    def test_manifest_marks_a_never_uploaded_file_as_having_no_object(self) -> None:
        FsNodeFileFactory(
            name="empty.txt",
            object_key="",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=0,
        )

        job = create_archive_job(self.user, self.root)

        item = job.items.get(zip_path="empty.txt")
        self.assertEqual(item.object_key, "")
        self.assertIsNone(item.storage_object)

    def test_snapshot_ignores_changes_after_the_job_is_created(self) -> None:
        job = create_archive_job(self.user, self.root)
        paths_before = [item.zip_path for item in self._items(job)]

        FsNodeFileFactory(
            name="new.txt",
            object_key="uploads/new/new.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=5,
        )
        self.file1.name = "renamed.txt"
        self.file1.save(update_fields=("name", "modified_at"))

        job.refresh_from_db()
        self.assertEqual(job.total_files, 2)
        self.assertEqual([item.zip_path for item in self._items(job)], paths_before)
        self.assertEqual(
            job.items.get(zip_path="a.txt").node_id,
            self.file1.pk,
        )

    def test_deleting_a_file_inside_the_root_keeps_the_snapshot(self) -> None:
        job = create_archive_job(self.user, self.root)

        remove_fs_node(self.user, self.file1.pk)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)
        self.assertTrue(job.items.filter(zip_path="a.txt").exists())
        self.assertTrue(FsNode.objects.filter(pk=self.file1.pk).exists())

    def test_deleting_the_root_cancels_the_job_and_releases_the_manifest(self) -> None:
        job = create_archive_job(self.user, self.root)

        remove_fs_node(self.user, self.root.pk)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.CANCELLED)
        self.assertTrue(job.cancel_requested)
        self.assertFalse(job.items.exists())
        # The rows are tombstones until the deletion worker runs.
        self.assertTrue(FsNode.objects.filter(pk=self.root.pk).exists())

        # Without the manifest PROTECT, the deletion worker can now finish.
        call_command(
            "run_deletion_worker",
            "--once",
            stdout=StringIO(),
            stderr=StringIO(),
        )
        self.assertFalse(FsNode.objects.filter(pk=self.root.pk).exists())

        with self.assertRaises(exceptions.FsNodeNotFoundError):
            create_archive_job(self.user, self.root)

    def test_duplicate_request_returns_the_active_job(self) -> None:
        job1 = create_archive_job(self.user, self.root)
        job2 = create_archive_job(self.user, self.root)

        self.assertEqual(job1.pk, job2.pk)
        self.assertEqual(FsNodeArchiveJob.objects.count(), 1)
        self.assertEqual(job1.items.count(), 4)

    def test_changed_tree_creates_a_new_snapshot(self) -> None:
        job1 = create_archive_job(self.user, self.root)

        FsNodeFileFactory(
            name="new.txt",
            object_key="uploads/new/new.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=5,
        )
        job2 = create_archive_job(self.user, self.root)

        self.assertNotEqual(job1.pk, job2.pk)
        self.assertEqual(job2.total_files, 3)
        self.assertTrue(job2.items.filter(zip_path="new.txt").exists())
        self.assertTrue(job1.items.filter(zip_path="a.txt").exists())
        self.assertFalse(job1.items.filter(zip_path="new.txt").exists())

    def test_other_user_cannot_request_the_archive(self) -> None:
        other_user = UserFactory()

        with self.assertRaises(exceptions.PermissionDenied):
            create_archive_job(other_user, self.root)

    def test_file_cannot_be_archived(self) -> None:
        with self.assertRaises(exceptions.FsNodeIsNotADirectoryError):
            create_archive_job(self.user, self.file1)

    def test_anonymous_user_without_share_is_rejected(self) -> None:
        with self.assertRaises(exceptions.PermissionDenied):
            create_archive_job(None, self.root)

    @override_settings(DIRECTORY_ARCHIVE_MAX_FILES=1)
    def test_file_limit_is_enforced(self) -> None:
        with self.assertRaises(exceptions.ArchiveLimitExceeded):
            create_archive_job(self.user, self.root)

        self.assertFalse(FsNodeArchiveJob.objects.exists())

    @override_settings(DIRECTORY_ARCHIVE_MAX_SIZE=15)
    def test_byte_limit_is_enforced(self) -> None:
        with self.assertRaises(exceptions.ArchiveLimitExceeded):
            create_archive_job(self.user, self.root)

        self.assertFalse(FsNodeArchiveJob.objects.exists())

    def test_snapshot_is_retried_after_a_concurrent_delete(self) -> None:
        real_bulk_create = FsNodeArchiveItem.objects.bulk_create
        calls = []

        def flaky_bulk_create(objs, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise IntegrityError("simulated concurrent deletion")
            return real_bulk_create(objs, *args, **kwargs)

        with patch.object(
            FsNodeArchiveItem.objects,
            "bulk_create",
            side_effect=flaky_bulk_create,
        ):
            job = create_archive_job(self.user, self.root)

        self.assertEqual(len(calls), 2)
        self.assertEqual(job.items.count(), 4)

    def test_share_access_and_revocation(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)

        job = create_archive_job(None, self.root, share=share)
        self.assertIsNone(job.requested_by)

        revoke_public_share(self.user, share.token)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.CANCELLED)
        self.assertFalse(job.items.exists())

    def test_revoked_share_cannot_create_a_snapshot(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.root, owner=self.user)
        share.revoked_at = now()
        share.save(update_fields=("revoked_at",))

        with self.assertRaises(exceptions.PermissionDenied):
            create_archive_job(None, self.root, share=share)

    def test_share_must_point_to_the_requested_root(self) -> None:
        share = SharedNodeFactory(root_fs_node=self.subdir, owner=self.user)

        with self.assertRaises(exceptions.PermissionDenied):
            create_archive_job(None, self.root, share=share)
