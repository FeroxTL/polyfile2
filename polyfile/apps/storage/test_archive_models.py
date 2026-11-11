import uuid

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from polyfile.apps.storage.factories import (
    FsNodeArchiveItemFactory,
    FsNodeArchiveJobFactory,
    FsNodeFileFactory,
    PendingObjectDeletionFactory,
)
from polyfile.apps.storage.models import (
    FsNode,
    FsNodeArchiveItem,
    FsNodeArchiveJob,
    PendingObjectDeletion,
)
from polyfile.apps.storage.storage_objects import StorageObjectRef


class ArchiveModelTests(TestCase):
    def test_fsnode_size_is_big_integer(self) -> None:
        self.assertEqual(
            FsNode._meta.get_field("size").get_internal_type(),
            "PositiveBigIntegerField",
        )

        node = FsNodeFileFactory(size=3_000_000_000)
        node.refresh_from_db()
        self.assertEqual(node.size, 3_000_000_000)

    def test_archive_job_defaults(self) -> None:
        job = FsNodeArchiveJobFactory()

        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)
        self.assertEqual(job.total_files, 0)
        self.assertEqual(job.total_bytes, 0)
        self.assertEqual(job.archive_key, "")
        self.assertFalse(job.cancel_requested)

    def test_root_node_uuid_is_not_a_foreign_key(self) -> None:
        job = FsNodeArchiveJobFactory(root_node_uuid=uuid.uuid4())

        self.assertIsNone(FsNodeArchiveJob._meta.get_field("root_node_uuid").remote_field)
        self.assertIsNotNone(job.root_node_uuid)

    def test_active_archive_job_is_unique_by_root_and_fingerprint(self) -> None:
        root_node_uuid = uuid.uuid4()
        fingerprint = "a" * 64
        FsNodeArchiveJobFactory(
            root_node_uuid=root_node_uuid,
            fingerprint=fingerprint,
            status=FsNodeArchiveJob.Status.PENDING,
        )

        with transaction.atomic(), self.assertRaises(IntegrityError):
            FsNodeArchiveJobFactory(
                root_node_uuid=root_node_uuid,
                fingerprint=fingerprint,
                status=FsNodeArchiveJob.Status.RUNNING,
            )

    def test_terminal_archive_job_does_not_block_new_job(self) -> None:
        root_node_uuid = uuid.uuid4()
        fingerprint = "b" * 64
        FsNodeArchiveJobFactory(
            root_node_uuid=root_node_uuid,
            fingerprint=fingerprint,
            status=FsNodeArchiveJob.Status.FAILED,
        )

        job = FsNodeArchiveJobFactory(
            root_node_uuid=root_node_uuid,
            fingerprint=fingerprint,
            status=FsNodeArchiveJob.Status.PENDING,
        )

        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)

    def test_archive_item_protects_node(self) -> None:
        item = FsNodeArchiveItemFactory()

        with self.assertRaises(ProtectedError):
            FsNode.objects.filter(pk=item.node_id).delete()

        item.delete()
        FsNode.objects.filter(pk=item.node_id).delete()
        self.assertFalse(FsNode.objects.filter(pk=item.node_id).exists())

    def test_archive_item_allows_multiple_directories_without_node(self) -> None:
        job = FsNodeArchiveJobFactory()

        FsNodeArchiveItem.objects.create(
            job=job,
            node=None,
            entry_type=FsNodeArchiveItem.EntryType.DIRECTORY,
            zip_path="empty/",
            position=0,
        )
        FsNodeArchiveItem.objects.create(
            job=job,
            node=None,
            entry_type=FsNodeArchiveItem.EntryType.DIRECTORY,
            zip_path="nested/",
            position=1,
        )

        self.assertEqual(job.items.count(), 2)

    def test_archive_item_node_is_unique_per_job(self) -> None:
        job = FsNodeArchiveJobFactory()
        node = FsNodeFileFactory()
        FsNodeArchiveItemFactory(job=job, node=node, zip_path="one.txt", position=0)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            FsNodeArchiveItemFactory(job=job, node=node, zip_path="two.txt", position=1)

    def test_archive_item_zip_path_is_unique_per_job(self) -> None:
        job = FsNodeArchiveJobFactory()
        FsNodeArchiveItemFactory(job=job, zip_path="same.txt", position=0)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            FsNodeArchiveItemFactory(job=job, zip_path="same.txt", position=1)

    def test_archive_item_position_is_unique_per_job(self) -> None:
        job = FsNodeArchiveJobFactory()
        FsNodeArchiveItemFactory(job=job, zip_path="one.txt", position=0)

        with transaction.atomic(), self.assertRaises(IntegrityError):
            FsNodeArchiveItemFactory(job=job, zip_path="two.txt", position=0)

    def test_archive_job_delete_cascades_items_but_keeps_nodes(self) -> None:
        item = FsNodeArchiveItemFactory()
        node_id = item.node_id

        item.job.delete()

        self.assertFalse(FsNodeArchiveItem.objects.filter(pk=item.pk).exists())
        self.assertTrue(FsNode.objects.filter(pk=node_id).exists())

    def test_pending_object_deletion_is_unique_by_storage_and_key(self) -> None:
        PendingObjectDeletionFactory(storage_id=1, object_key="uploads/1/file.txt")

        with transaction.atomic(), self.assertRaises(IntegrityError):
            PendingObjectDeletionFactory(storage_id=1, object_key="uploads/1/file.txt")

        self.assertEqual(PendingObjectDeletion.objects.count(), 1)

    def test_pending_object_deletion_exposes_storage_object(self) -> None:
        row = PendingObjectDeletionFactory(
            storage_id=7,
            object_key="uploads/7/file.txt",
        )

        self.assertEqual(
            row.storage_object,
            StorageObjectRef(7, "uploads/7/file.txt"),
        )

    def test_fsnode_storage_object_uses_the_uploaded_file(self) -> None:
        node = FsNodeFileFactory(file="uploads/1/file.txt")

        self.assertEqual(
            node.storage_object,
            StorageObjectRef(node.storage_id, "uploads/1/file.txt"),
        )

    def test_fsnode_storage_object_is_none_without_an_upload(self) -> None:
        node = FsNodeFileFactory(file="")

        self.assertIsNone(node.storage_object)
