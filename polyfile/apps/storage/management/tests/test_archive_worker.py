import hashlib
import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.archive import create_archive_job
from polyfile.apps.storage.archive_backend import FileSystemArchiveBackend
from polyfile.apps.storage.factories import (
    FsNodeArchiveJobFactory,
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
)
from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.management.archive_job_strategies import (
    RelationalArchiveClaimStrategy,
    SQLiteArchiveClaimStrategy,
)
from polyfile.apps.storage.models import (
    FsNodeArchiveJob,
    FsStorage,
)
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path

LOGGER_NAME = "polyfile.apps.storage.management.commands.run_archive_worker"


def run_worker(**options) -> str:
    """Run the archive worker exactly once with output captured."""
    stdout = StringIO()
    call_command(
        "run_archive_worker",
        "--once",
        stdout=stdout,
        stderr=StringIO(),
        **options,
    )
    return stdout.getvalue()


class ArchiveBackendTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.backend = FileSystemArchiveBackend(self.temp_dir.name)

    def test_rejects_keys_outside_the_archive_root(self) -> None:
        with self.assertRaises(ValueError):
            self.backend.path("../escape.zip")
        with self.assertRaises(ValueError):
            self.backend.path("/absolute.zip")

    def test_publish_is_atomic_and_missing_delete_is_ignored(self) -> None:
        self.backend.save_stream("archives/aa/test.zip", BytesIO(b"data"))
        self.assertTrue(self.backend.exists("archives/aa/test.zip"))
        self.assertEqual(self.backend.size("archives/aa/test.zip"), 4)

        self.backend.delete("archives/aa/missing.zip")
        self.assertFalse(self.backend.exists("archives/aa/missing.zip"))


class ArchiveClaimStrategyTests(TestCase):
    def test_sqlite_claim_marks_the_job_running(self) -> None:
        job = FsNodeArchiveJobFactory(status=FsNodeArchiveJob.Status.PENDING)

        claimed = SQLiteArchiveClaimStrategy().claim_job("host:1", 60)

        self.assertEqual(claimed.pk, job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.RUNNING)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(job.locked_by, "host:1")
        self.assertIsNotNone(job.started_at)
        self.assertIsNotNone(job.locked_until)

    def test_relational_claim_marks_the_job_running(self) -> None:
        job = FsNodeArchiveJobFactory(status=FsNodeArchiveJob.Status.PENDING)

        claimed = RelationalArchiveClaimStrategy().claim_job("host:1", 60)

        self.assertEqual(claimed.pk, job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.RUNNING)
        self.assertEqual(job.attempts, 1)

    def test_claim_ignores_a_job_scheduled_in_the_future(self) -> None:
        job = FsNodeArchiveJobFactory(status=FsNodeArchiveJob.Status.PENDING)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            scheduled_at=now() + timedelta(minutes=5),
        )

        self.assertIsNone(SQLiteArchiveClaimStrategy().claim_job("host:1", 60))
        self.assertIsNone(RelationalArchiveClaimStrategy().claim_job("host:1", 60))


@override_settings(DIRECTORY_ARCHIVE_TTL=timedelta(hours=2))
class ArchiveWorkerTests(TestCase):
    def setUp(self) -> None:
        self.source_dir = tempfile.TemporaryDirectory()
        self.archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_dir.cleanup)
        self.addCleanup(self.archive_dir.cleanup)

        self.settings_override = override_settings(
            ARCHIVE_ROOT=Path(self.archive_dir.name),
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.storage = FsStorage.objects.create(
            name="Local disk",
            backend=get_storage_path(FileSystemBackend),
            options={"location": self.source_dir.name, "upload_to": ""},
        )
        fs_storages.clear()
        self.addCleanup(fs_storages.clear)

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
        self.file1 = self._create_file("a.txt", b"aaa", parent=self.root)
        self.file2 = self._create_file("b.txt", b"bbbb", parent=self.subdir)

    def _create_file(self, name: str, content: bytes, parent) -> object:
        Path(self.source_dir.name, name).write_bytes(content)
        return FsNodeFileFactory(
            name=name,
            file=name,
            owner=self.user,
            storage=self.storage,
            parent=parent,
            size=len(content),
            md5=hashlib.md5(content).hexdigest(),
        )

    def _archive_path(self, job: FsNodeArchiveJob) -> Path:
        return Path(self.archive_dir.name, job.archive_key)

    def _expected_key(self, job: FsNodeArchiveJob) -> Path:
        job_id = str(job.pk)
        return Path(self.archive_dir.name, "archives", job_id[:2], f"{job_id}.zip")

    def test_worker_builds_a_complete_ordered_archive(self) -> None:
        job = create_archive_job(self.user, self.root)
        expected_paths = list(
            job.items.order_by("position").values_list("zip_path", flat=True)
        )

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.READY)
        self.assertEqual(job.processed_files, 2)
        self.assertEqual(job.processed_bytes, 7)
        self.assertEqual(job.archive_size, self._archive_path(job).stat().st_size)
        self.assertEqual(
            job.archive_md5,
            hashlib.md5(self._archive_path(job).read_bytes()).hexdigest(),
        )
        self.assertEqual(job.finished_at + timedelta(hours=2), job.expires_at)
        self.assertFalse(job.items.exists())

        with zipfile.ZipFile(self._archive_path(job)) as archive:
            self.assertEqual(archive.namelist(), expected_paths)
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.read("a.txt"), b"aaa")
            self.assertEqual(archive.read("sub/b.txt"), b"bbbb")
            self.assertTrue(archive.getinfo("empty/").is_dir())

    def test_worker_logs_a_successful_archive(self) -> None:
        job = create_archive_job(self.user, self.root)

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            output = run_worker()

        messages = "\n".join(logs.output)
        self.assertIn(f"job={job.pk}", messages)
        self.assertIn("Building archive", messages)
        self.assertIn("manifest written", messages)
        self.assertIn(f"Archive job {job.pk} ready", messages)
        self.assertIn(f"Archive job {job.pk} ready", output)

    def test_worker_logs_cancellation(self) -> None:
        job = create_archive_job(self.user, self.root)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(cancel_requested=True)

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            output = run_worker()

        messages = "\n".join(logs.output)
        self.assertIn(f"Archive job {job.pk} cancelled", messages)
        self.assertIn(f"Archive job {job.pk} cancelled", output)

    def test_worker_logs_retry_and_permanent_failure(self) -> None:
        job = create_archive_job(self.user, self.root)

        with patch.object(
            FileSystemBackend,
            "open",
            side_effect=OSError("storage is unavailable"),
        ), self.assertLogs(LOGGER_NAME, level="WARNING") as retry_logs:
            run_worker()

        self.assertIn(
            f"Archive job {job.pk} will be retried",
            "\n".join(retry_logs.output),
        )

        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            scheduled_at=now() - timedelta(seconds=1),
        )
        with patch.object(
            FileSystemBackend,
            "open",
            side_effect=OSError("storage is unavailable"),
        ), self.assertLogs(LOGGER_NAME, level="ERROR") as failure_logs:
            run_worker(max_attempts=1)

        self.assertIn(
            f"Archive job {job.pk} failed permanently",
            "\n".join(failure_logs.output),
        )

    def test_worker_logs_stale_job_requeue_and_failure(self) -> None:
        requeued = create_archive_job(self.user, self.root)
        FsNodeArchiveJob.objects.filter(pk=requeued.pk).update(
            status=FsNodeArchiveJob.Status.RUNNING,
            attempts=1,
            locked_by="dead-worker",
            locked_until=now() - timedelta(seconds=1),
        )

        with self.assertLogs(LOGGER_NAME, level="INFO") as logs:
            run_worker()

        self.assertIn("Requeued 1 stale archive job(s)", "\n".join(logs.output))

        failed = create_archive_job(self.user, self.subdir)
        FsNodeArchiveJob.objects.filter(pk=failed.pk).update(
            status=FsNodeArchiveJob.Status.RUNNING,
            attempts=3,
            locked_by="dead-worker",
            locked_until=now() - timedelta(seconds=1),
        )

        with self.assertLogs(LOGGER_NAME, level="WARNING") as failed_logs:
            run_worker(max_attempts=3)

        self.assertIn(
            f"Marked 1 stale archive job(s) as failed after max attempts: {failed.pk}",
            "\n".join(failed_logs.output),
        )

    def test_worker_writes_empty_file_nodes(self) -> None:
        FsNodeFileFactory(
            name="empty.txt",
            file="",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=0,
        )
        job = create_archive_job(self.user, self.root)

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.READY)
        with zipfile.ZipFile(self._archive_path(job)) as archive:
            self.assertEqual(archive.read("empty.txt"), b"")

    def test_cancelled_job_does_not_publish_an_archive(self) -> None:
        job = create_archive_job(self.user, self.root)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(cancel_requested=True)

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.CANCELLED)
        self.assertFalse(job.items.exists())
        self.assertFalse(self._expected_key(job).exists())
        self.assertFalse(list(Path(self.archive_dir.name).rglob("*.part")))

    def test_missing_object_fails_the_job_and_releases_the_manifest(self) -> None:
        job = create_archive_job(self.user, self.root)
        Path(self.source_dir.name, "a.txt").unlink()

        with self.assertLogs(LOGGER_NAME, level="ERROR") as logs:
            run_worker()

        self.assertIn(
            f"Archive job {job.pk} failed permanently",
            "\n".join(logs.output),
        )
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.FAILED)
        self.assertFalse(job.items.exists())
        self.assertFalse(self._expected_key(job).exists())
        self.assertFalse(list(Path(self.archive_dir.name).rglob("*.part")))
        self.assertIn("a.txt", job.last_error)

    def test_transient_storage_error_is_retried(self) -> None:
        job = create_archive_job(self.user, self.root)

        with patch.object(
            FileSystemBackend,
            "open",
            side_effect=OSError("storage is unavailable"),
        ), self.assertLogs(LOGGER_NAME, level="WARNING") as logs:
            run_worker()

        self.assertIn(
            f"Archive job {job.pk} will be retried",
            "\n".join(logs.output),
        )
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)
        self.assertEqual(job.attempts, 1)
        self.assertGreater(job.scheduled_at, now())
        self.assertTrue(job.items.exists())
        self.assertFalse(self._expected_key(job).exists())
        self.assertFalse(list(Path(self.archive_dir.name).rglob("*.part")))

        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            scheduled_at=now() - timedelta(seconds=1),
        )
        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.READY)

    def test_job_fails_after_max_attempts(self) -> None:
        job = create_archive_job(self.user, self.root)

        with patch.object(
            FileSystemBackend,
            "open",
            side_effect=OSError("storage is unavailable"),
        ), self.assertLogs(LOGGER_NAME, level="ERROR") as logs:
            run_worker(max_attempts=1)

        self.assertIn(
            f"Archive job {job.pk} failed permanently",
            "\n".join(logs.output),
        )
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.FAILED)
        self.assertFalse(job.items.exists())
        self.assertFalse(self._expected_key(job).exists())

    def test_worker_skips_a_job_scheduled_in_the_future(self) -> None:
        job = create_archive_job(self.user, self.root)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            scheduled_at=now() + timedelta(minutes=5),
        )

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)
        self.assertTrue(job.items.exists())
        self.assertFalse(self._expected_key(job).exists())

    def test_worker_reanimates_a_stale_job(self) -> None:
        job = create_archive_job(self.user, self.root)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            status=FsNodeArchiveJob.Status.RUNNING,
            attempts=1,
            locked_by="dead-worker",
            locked_until=now() - timedelta(seconds=1),
        )

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.READY)

    def test_stale_job_past_max_attempts_fails_and_releases_the_manifest(self) -> None:
        job = create_archive_job(self.user, self.root)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            status=FsNodeArchiveJob.Status.RUNNING,
            attempts=3,
            locked_by="dead-worker",
            locked_until=now() - timedelta(seconds=1),
        )

        with self.assertLogs(LOGGER_NAME, level="WARNING") as logs:
            run_worker(max_attempts=3)

        self.assertIn(
            f"Marked 1 stale archive job(s) as failed after max attempts: {job.pk}",
            "\n".join(logs.output),
        )
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.FAILED)
        self.assertFalse(job.items.exists())
        self.assertFalse(self._expected_key(job).exists())

    def test_worker_enables_zip64(self) -> None:
        create_archive_job(self.user, self.root)
        calls = {}
        real_zip_file = zipfile.ZipFile

        def fake_zip_file(*args, **kwargs):
            calls.update(kwargs)
            return real_zip_file(*args, **kwargs)

        with patch(
            "polyfile.apps.storage.management.commands.run_archive_worker.zipfile.ZipFile",
            side_effect=fake_zip_file,
        ):
            run_worker()

        self.assertTrue(calls["allowZip64"])
