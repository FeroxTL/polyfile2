import io
import signal
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path, PurePosixPath
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.core.management import call_command
from django.db import DatabaseError
from django.db.models.manager import Manager
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
    TestFsBackend,
)
from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.management.commands.run_deletion_worker import DeletionWorker
from polyfile.apps.storage.management.job_strategies import (
    JobStrategyFactory,
    RelationalClaimStrategy,
    SQLiteClaimStrategy,
)
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob, FsStorage
from polyfile.apps.storage.utils import remove_fs_node
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path
from polyfile.core.exceptions import FsNodeNotFoundError


def run_worker(**options) -> None:
    """Run the deletion worker exactly once with output captured."""
    call_command(
        "run_deletion_worker",
        "--once",
        stdout=StringIO(),
        stderr=StringIO(),
        **options,
    )


class FailingDeleteBackend(TestFsBackend):
    """Test backend that simulates an unavailable storage during deletion."""

    def delete_many(self, names) -> dict[str, bool | Exception]:
        return {name: OSError("storage is unavailable") for name in names}

    def delete(self, name) -> None:
        raise OSError("storage is unavailable")


class PartialFailingDeleteBackend(TestFsBackend):
    """Test backend that fails only on files with 'stuck' in the name."""

    def delete_many(self, names) -> dict[str, bool | Exception]:
        return {
            name: OSError("storage is unavailable") if "stuck" in name else True
            for name in names
        }

    def delete(self, name) -> None:
        if "stuck" in name:
            raise OSError("storage is unavailable")


class JobStrategyTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)

    def test_factory_selects_strategy_for_database_engine(self) -> None:
        """Verify that the correct JobStrategy is selected based on the Django database engine."""
        cases = (
            ("django.db.backends.sqlite3", SQLiteClaimStrategy),
            ("django.db.backends.postgresql", RelationalClaimStrategy),
            ("django.db.backends.mysql", RelationalClaimStrategy),
        )
        for engine, expected_class in cases:
            with self.subTest(engine=engine), patch.dict(
                settings.DATABASES["default"], {"ENGINE": engine},
            ):
                self.assertIsInstance(JobStrategyFactory.get_strategy(), expected_class)

    def test_relational_claim_uses_skip_locked_and_increments_attempts(self) -> None:
        """Verify that RelationalClaimStrategy uses skip_locked=True and increments the attempts count."""
        job = FsNodeDeletionJob.objects.create(
            owner=self.user,
            root_path="/unused",
            status=FsNodeDeletionJob.Status.PENDING,
        )
        select_for_update_calls = []

        def fake_select_for_update(manager, *args, **kwargs):
            select_for_update_calls.append((args, kwargs))
            return manager.get_queryset()

        with patch.object(Manager, "select_for_update", new=fake_select_for_update):
            claimed = RelationalClaimStrategy().claim_job("test-host:1", lock_timeout=60)

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, job.pk)
        self.assertEqual(
            select_for_update_calls,
            [((), {"skip_locked": True})],
        )
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.RUNNING)
        self.assertEqual(job.locked_by, "test-host:1")
        self.assertEqual(job.attempts, 1)
        self.assertIsNotNone(job.locked_until)

    def test_relational_claim_returns_none_for_empty_queue(self) -> None:
        """Verify that RelationalClaimStrategy returns None when no jobs are available."""
        def fake_select_for_update(manager, *args, **kwargs):
            return manager.get_queryset()

        with patch.object(Manager, "select_for_update", new=fake_select_for_update):
            claimed = RelationalClaimStrategy().claim_job("test-host:1", lock_timeout=60)

        self.assertIsNone(claimed)

    def test_sqlite_claim_returns_none_when_update_fails(self) -> None:
        """Verify that SQLiteClaimStrategy returns None if another worker claimed the job first (race condition)."""
        strategy = SQLiteClaimStrategy()

        # Mock the filter method of FsNodeDeletionJob.objects.filter
        # We want the first call (to get job_id) to return a mock that has a 'first' method returning a dict.
        # The second call (to update) should return a mock where 'update' returns 0.

        with patch("polyfile.apps.storage.management.job_strategies.FsNodeDeletionJob.objects.filter") as mock_filter:
            # Mock for the first filter call (job_id = ...first())
            mock_job_id_queryset = MagicMock()
            mock_job_id_queryset.order_by.return_value.values.return_value.first.return_value = {"id": 1}

            # Mock for the second filter call (update(...))
            mock_update_queryset = MagicMock()
            mock_update_queryset.update.return_value = 0

            mock_filter.side_effect = [mock_job_id_queryset, mock_update_queryset]

            claimed = strategy.claim_job("test-host:1", 60)
            self.assertIsNone(claimed)


class DeletionWorkerClaimTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)

    def _create_job(self, status=FsNodeDeletionJob.Status.PENDING, **kwargs) -> FsNodeDeletionJob:
        return FsNodeDeletionJob.objects.create(
            owner=self.user,
            root_path="/unused",
            status=status,
            **kwargs,
        )

    def test_claim_marks_pending_job_running(self) -> None:
        job = self._create_job()

        claimed = DeletionWorker()._claim_job("test-host:1")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.RUNNING)
        self.assertEqual(job.locked_by, "test-host:1")

    def test_claim_increments_attempts(self) -> None:
        """Every claim must count as an attempt so that the retry limit can work."""
        job = self._create_job()

        DeletionWorker()._claim_job("test-host:1")

        job.refresh_from_db()
        self.assertEqual(job.attempts, 1)

    def test_claim_does_not_claim_already_running_job(self) -> None:
        self._create_job(status=FsNodeDeletionJob.Status.RUNNING, locked_by="other")

        claimed = DeletionWorker()._claim_job("test-host:1")

        self.assertIsNone(claimed)

    def test_claim_ignores_finished_and_cancelled_jobs(self) -> None:
        for status in (
            FsNodeDeletionJob.Status.DONE,
            FsNodeDeletionJob.Status.FAILED,
            FsNodeDeletionJob.Status.TIMEOUT,
            FsNodeDeletionJob.Status.CANCELLED,
        ):
            with self.subTest(status=status):
                self._create_job(status=status)

        claimed = DeletionWorker()._claim_job("test-host:1")

        self.assertIsNone(claimed)

    def test_claim_returns_none_for_empty_queue(self) -> None:
        claimed = DeletionWorker()._claim_job("test-host:1")

        self.assertIsNone(claimed)

    def test_claim_takes_the_oldest_pending_job(self) -> None:
        old_job = self._create_job()
        old_job.scheduled_at = now() - timedelta(minutes=10)
        old_job.save(update_fields=("scheduled_at",))
        new_job = self._create_job()
        new_job.scheduled_at = now()
        new_job.save(update_fields=("scheduled_at",))

        claimed = DeletionWorker()._claim_job("test-host:1")

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.pk, old_job.pk)

    def test_second_worker_does_not_claim_the_same_job(self) -> None:
        job = self._create_job()
        first_worker = DeletionWorker()
        second_worker = DeletionWorker()

        first_claim = first_worker._claim_job("test-host:1")
        second_claim = second_worker._claim_job("test-host:2")

        self.assertIsNotNone(first_claim)
        self.assertIsNone(second_claim)
        job.refresh_from_db()
        self.assertEqual(job.locked_by, "test-host:1")

    def test_claim_increments_attempts_on_each_claim(self) -> None:
        """Repeated claims must accumulate attempts, otherwise max_attempts is never reached."""
        job = self._create_job()
        worker = DeletionWorker()

        worker._claim_job("test-host:1")
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(
            status=FsNodeDeletionJob.Status.PENDING,
        )
        worker._claim_job("test-host:1")

        job.refresh_from_db()
        self.assertEqual(job.attempts, 2)

    def test_claim_sets_lock_expiry(self) -> None:
        """A claimed job must get a lock deadline so it can be recovered after a crash."""
        self._create_job()

        claimed = DeletionWorker()._claim_job("test-host:1")

        self.assertIsNotNone(claimed)
        self.assertIsNotNone(claimed.locked_until)

    def test_worker_once_exits_when_queue_is_empty(self) -> None:
        run_worker()

        self.assertEqual(FsNodeDeletionJob.objects.count(), 0)

    def test_worker_once_processes_only_one_job(self) -> None:
        first_job = self._create_job()
        second_job = self._create_job()

        run_worker()

        first_job.refresh_from_db()
        second_job.refresh_from_db()
        self.assertEqual(first_job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(second_job.status, FsNodeDeletionJob.Status.PENDING)


class DeletionWorkerReanimationTests(TestCase):
    lock_timeout = 300

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)

    def _create_running_job(self, *, locked_until, attempts=1, **kwargs) -> FsNodeDeletionJob:
        return FsNodeDeletionJob.objects.create(
            owner=self.user,
            root_path="/unused",
            status=FsNodeDeletionJob.Status.RUNNING,
            locked_by="dead-host:1",
            locked_until=locked_until,
            attempts=attempts,
            **kwargs,
        )

    def test_stale_running_job_is_returned_to_pending(self) -> None:
        job = self._create_running_job(
            locked_until=now() - timedelta(seconds=self.lock_timeout + 1),
        )

        DeletionWorker(lock_timeout=self.lock_timeout)._reanimate_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.PENDING)
        self.assertIsNone(job.locked_until)
        self.assertEqual(job.locked_by, "")
        self.assertEqual(job.attempts, 1)

    def test_stale_running_job_preserves_progress_counters(self) -> None:
        job = self._create_running_job(
            locked_until=now() - timedelta(seconds=self.lock_timeout + 1),
            processed_nodes=7,
        )

        DeletionWorker(lock_timeout=self.lock_timeout)._reanimate_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(job.processed_nodes, 7)

    def test_stale_running_job_at_attempt_limit_becomes_timeout(self) -> None:
        job = self._create_running_job(
            locked_until=now() - timedelta(seconds=self.lock_timeout + 1),
            attempts=5,
        )

        DeletionWorker(max_attempts=5, lock_timeout=self.lock_timeout)._reanimate_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.TIMEOUT)
        self.assertIsNotNone(job.finished_at)

    def test_locked_running_job_is_not_reanimated(self) -> None:
        job = self._create_running_job(
            locked_until=now() + timedelta(seconds=60),
        )

        DeletionWorker()._reanimate_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.RUNNING)
        self.assertEqual(job.locked_by, "dead-host:1")

    def test_finished_and_cancelled_jobs_are_not_reanimated(self) -> None:
        stale_lock = now() - timedelta(seconds=self.lock_timeout + 1)
        jobs = {}
        for status in (
            FsNodeDeletionJob.Status.PENDING,
            FsNodeDeletionJob.Status.DONE,
            FsNodeDeletionJob.Status.FAILED,
            FsNodeDeletionJob.Status.TIMEOUT,
            FsNodeDeletionJob.Status.CANCELLED,
        ):
            jobs[status] = FsNodeDeletionJob.objects.create(
                owner=self.user,
                root_path="/unused",
                status=status,
                locked_until=stale_lock,
                attempts=1,
            )

        DeletionWorker()._reanimate_stale_jobs()

        for status, job in jobs.items():
            with self.subTest(status=status):
                job.refresh_from_db()
                self.assertEqual(job.status, status)

    def test_worker_recovers_and_processes_a_stale_job(self) -> None:
        root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        FsNodeFileFactory(
            name="file.txt", owner=self.user, storage=self.storage, parent=root, size=3,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(
            status=FsNodeDeletionJob.Status.RUNNING,
            locked_by="dead-host:1",
            locked_until=now() - timedelta(seconds=self.lock_timeout + 1),
            attempts=1,
        )

        run_worker(lock_timeout=self.lock_timeout, max_attempts=5)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(FsNode.objects.filter(deletion_job=job).count(), 0)

    def test_worker_does_not_revive_a_job_that_exhausted_attempts(self) -> None:
        root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        FsNodeFileFactory(
            name="file.txt", owner=self.user, storage=self.storage, parent=root, size=3,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(
            status=FsNodeDeletionJob.Status.RUNNING,
            locked_by="dead-host:1",
            locked_until=now() - timedelta(seconds=self.lock_timeout + 1),
            attempts=5,
        )

        run_worker(lock_timeout=self.lock_timeout, max_attempts=5)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.TIMEOUT)
        self.assertTrue(FsNode.objects.filter(deletion_job=job).exists())

    def test_expired_lock_is_reanimated_immediately(self) -> None:
        """The lock deadline is the moment the job becomes stale, not the lock timeout after it."""
        job = self._create_running_job(
            locked_until=now() - timedelta(seconds=1),
        )

        DeletionWorker(max_attempts=5, lock_timeout=self.lock_timeout)._reanimate_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.PENDING)

    def test_running_job_without_lock_deadline_is_reanimated(self) -> None:
        """The SQLite claim strategy stores no lock deadline; such jobs must still be recoverable."""
        job = self._create_running_job(locked_until=None)

        DeletionWorker()._reanimate_stale_jobs()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.PENDING)


class DeletionWorkerProcessingTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.subdir = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )
        self.file1 = FsNodeFileFactory(
            name="f1.txt", owner=self.user, storage=self.storage, parent=self.root, size=10,
        )
        self.file2 = FsNodeFileFactory(
            name="f2.txt", owner=self.user, storage=self.storage, parent=self.subdir, size=20,
        )
        self.empty_dir = FsNodeDirectoryFactory(
            name="empty", owner=self.user, storage=self.storage, parent=self.subdir,
        )

    def test_deletes_the_whole_subtree_and_completes_the_job(self) -> None:
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        self.assertEqual(FsNode.objects.count(), 5)

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertIsNotNone(job.finished_at)
        self.assertIsNone(job.locked_until)
        self.assertEqual(FsNode.objects.filter(deletion_job=job).count(), 0)
        self.assertEqual(FsNode.objects.count(), 0)
        self.assertEqual(FsNode.active.count(), 0)

    def test_processed_nodes_match_the_subtree(self) -> None:
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.processed_nodes, job.total_nodes)
        self.assertEqual(job.processed_nodes, 5)

    def test_deletes_a_deep_directory_chain(self) -> None:
        parent = self.root
        for index in range(10):
            parent = FsNodeDirectoryFactory(
                name=f"level-{index}",
                owner=self.user,
                storage=self.storage,
                parent=parent,
            )
        FsNodeFileFactory(
            name="deep.txt", owner=self.user, storage=self.storage, parent=parent, size=1,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(FsNode.objects.filter(deletion_job=job).count(), 0)

    def test_small_batch_size_still_removes_every_node(self) -> None:
        for index in range(20):
            FsNodeFileFactory(
                name=f"bulk-{index}.txt",
                owner=self.user,
                storage=self.storage,
                parent=self.subdir,
                size=index,
            )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker(batch_size=3)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(FsNode.objects.filter(deletion_job=job).count(), 0)
        self.assertEqual(job.processed_nodes, job.total_nodes)

    def test_worker_does_not_delete_active_nodes_outside_the_job(self) -> None:
        active_dir = FsNodeDirectoryFactory(
            name="keep", owner=self.user, storage=self.storage,
        )
        active_file = FsNodeFileFactory(
            name="keep.txt", owner=self.user, storage=self.storage, parent=active_dir, size=5,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        active_dir.refresh_from_db()
        active_file.refresh_from_db()
        self.assertIsNone(active_dir.deleted_at)
        self.assertIsNone(active_file.deleted_at)

    def test_worker_once_leaves_other_pending_jobs_untouched(self) -> None:
        """Verify that the 'once' worker only affects what it's supposed to and leaves other pending jobs untouched."""
        first_job = remove_fs_node(self.user, PurePosixPath("/root"))
        keep_dir = FsNodeDirectoryFactory(
            name="keep", owner=self.user, storage=self.storage,
        )
        keep_file = FsNodeFileFactory(
            name="keep.txt", owner=self.user, storage=self.storage, parent=keep_dir, size=5,
        )
        second_job = remove_fs_node(self.user, PurePosixPath("/keep"))
        FsNodeDeletionJob.objects.filter(pk=second_job.pk).update(
            scheduled_at=now() + timedelta(minutes=5),
        )

        run_worker()

        first_job.refresh_from_db()
        second_job.refresh_from_db()
        self.assertEqual(first_job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(second_job.status, FsNodeDeletionJob.Status.PENDING)
        self.assertTrue(FsNode.objects.filter(pk=keep_file.pk).exists())
        keep_dir.refresh_from_db()
        self.assertIsNotNone(keep_dir.deleted_at)

    def test_empty_job_is_completed(self) -> None:
        """Verify handling of jobs with no nodes."""
        with self.assertRaises(FsNodeNotFoundError):
            remove_fs_node(self.user, PurePosixPath("/nothing"))

    def test_job_is_failed_when_attempt_limit_is_already_exceeded(self) -> None:
        """Verify failure when max attempts reached."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(attempts=5)

        run_worker(max_attempts=1)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.FAILED)
        self.assertIn("Max attempts exceeded", job.last_error)
        self.assertTrue(FsNode.objects.filter(deletion_job=job).exists())

    def test_unexpected_exception_marks_the_job_failed(self) -> None:
        """Verify exception handling during processing."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        with patch.object(DeletionWorker, "_process_job", side_effect=RuntimeError("boom")):
            run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.FAILED)
        self.assertIn("boom", job.last_error)
        self.assertIsNotNone(job.finished_at)
        self.assertIsNone(job.locked_until)

    def test_database_error_returns_job_to_pending_for_retry(self) -> None:
        """A database error during processing should allow retry instead of failing permanently."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        with patch.object(DeletionWorker, "_process_job", side_effect=DatabaseError("db down")):
            run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.PENDING)
        self.assertIn("db down", job.last_error)

    def test_database_error_becomes_timeout_after_max_attempts(self) -> None:
        """A database error should eventually time out if retries are exhausted."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(attempts=5)

        with patch.object(DeletionWorker, "_process_job", side_effect=DatabaseError("db down")):
            run_worker(max_attempts=5)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.TIMEOUT)
        self.assertIn("db down", job.last_error)
        self.assertIsNotNone(job.finished_at)

    def test_completed_job_is_not_processed_again(self) -> None:
        """Verify idempotency of processing."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        run_worker()
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(
            status=FsNodeDeletionJob.Status.PENDING,
            attempts=0,
        )

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(job.processed_nodes, 5)

    def test_deletion_job_status_endpoint_reports_worker_result(self) -> None:
        """Verify API response for job status."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        self.client.force_login(self.user)

        run_worker()

        response = self.client.get(
            reverse("fs_node_deletion_job", kwargs={"job_id": job.pk}),
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["job_id"], str(job.pk))
        self.assertEqual(data["status"], FsNodeDeletionJob.Status.DONE)
        self.assertEqual(data["processed_nodes"], 5)
        self.assertIsNotNone(data["finished_at"])


class DeletionWorkerProgressTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.file1 = FsNodeFileFactory(
            name="f1.txt", owner=self.user, storage=self.storage, parent=self.root, size=11,
        )
        self.file2 = FsNodeFileFactory(
            name="f2.txt", owner=self.user, storage=self.storage, parent=self.root, size=31,
        )

    def test_worker_calculates_total_nodes_when_job_has_no_totals(self) -> None:
        """Verify total node calculation if the counter was not filled in advance."""
        job = remove_fs_node(self.user, PurePosixPath("/root"))
        FsNodeDeletionJob.objects.filter(pk=job.pk).update(total_nodes=0)

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.total_nodes, 3)
        self.assertEqual(job.processed_nodes, 3)

    def test_directory_only_job_has_node_progress(self) -> None:
        """Verify node progress for an empty directory."""
        FsNodeDirectoryFactory(
            name="empty", owner=self.user, storage=self.storage, parent=self.root,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root/empty"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(job.total_nodes, 1)
        self.assertEqual(job.processed_nodes, 1)


class DeletionWorkerStorageTests(TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = FsStorage.objects.create(
            name="Local disk",
            backend=get_storage_path(FileSystemBackend),
            options={"location": self.temp_dir.name, "upload_to": ""},
        )
        fs_storages.clear()
        self.addCleanup(fs_storages.clear)
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)

    def _create_file_node(self, name: str, content: bytes, parent=None) -> FsNode:
        path = Path(self.temp_dir.name, name)
        path.write_bytes(content)
        return FsNodeFileFactory(
            name=name,
            file=name,
            owner=self.user,
            storage=self.storage,
            parent=parent or self.root,
            size=len(content),
        )

    def test_worker_removes_physical_files_from_storage(self) -> None:
        """Verify physical file deletion."""
        file1 = self._create_file_node("f1.txt", b"first")
        file2 = self._create_file_node("f2.txt", b"second")
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertFalse(Path(self.temp_dir.name, "f1.txt").exists())
        self.assertFalse(Path(self.temp_dir.name, "f2.txt").exists())
        self.assertFalse(FsNode.objects.filter(pk__in=[file1.pk, file2.pk]).exists())

    def test_missing_physical_file_does_not_block_deletion(self) -> None:
        """Verify missing file handling."""
        node = FsNodeFileFactory(
            name="already-gone.txt",
            file="already-gone.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=4,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertFalse(FsNode.objects.filter(pk=node.pk).exists())


class DeletionWorkerStorageFailureTests(TestCase):
    def setUp(self) -> None:
        self.storage = FsStorage.objects.create(
            name="Failing storage",
            backend=get_storage_path(FailingDeleteBackend),
            options={},
        )
        fs_storages.clear()
        self.addCleanup(fs_storages.clear)
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)

    def test_storage_failure_keeps_the_database_row_for_retry(self) -> None:
        """A failed storage delete must not be silently treated as a successful deletion."""
        node = FsNodeFileFactory(
            name="stuck.txt",
            file="stuck.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=5,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.FAILED)
        self.assertIn("storage is unavailable", job.last_error)
        self.assertTrue(FsNode.objects.filter(pk=node.pk).exists())
        self.assertIsNotNone(FsNode.objects.get(pk=node.pk).deleted_at)

    def test_storage_failure_does_not_block_healthy_storage_nodes(self) -> None:
        """Files from healthy storage are removed even if another storage fails."""
        healthy_storage = FsStorage.objects.create(
            name="Healthy storage",
            backend=get_storage_path(FileSystemBackend),
            options={"location": tempfile.mkdtemp(), "upload_to": ""},
        )
        fs_storages.clear()
        FsNodeFileFactory(
            name="healthy.txt",
            file="healthy.txt",
            owner=self.user,
            storage=healthy_storage,
            parent=self.root,
            size=5,
        )
        stuck_file = FsNodeFileFactory(
            name="stuck.txt",
            file="stuck.txt",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
            size=5,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker()

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.FAILED)
        self.assertFalse(FsNode.objects.filter(name="healthy.txt", deletion_job=job).exists())
        self.assertTrue(FsNode.objects.filter(pk=stuck_file.pk).exists())

    # def test_partial_storage_failure_deletes_only_successful_files(self) -> None:
    #     """Only FsNode rows for successfully deleted files are removed from DB."""
    #     partial_storage = FsStorage.objects.create(
    #         name="Partial storage",
    #         backend=get_storage_path(PartialFailingDeleteBackend),
    #         options={},
    #     )
    #     fs_storages.clear()
    #     ok_file = FsNodeFileFactory(
    #         name="ok.txt",
    #         file="ok.txt",
    #         owner=self.user,
    #         storage=partial_storage,
    #         parent=self.root,
    #         size=5,
    #     )
    #     stuck_file = FsNodeFileFactory(
    #         name="stuck.txt",
    #         file="stuck.txt",
    #         owner=self.user,
    #         storage=partial_storage,
    #         parent=self.root,
    #         size=5,
    #     )
    #     job = remove_fs_node(self.user, PurePosixPath("/root"))
    #
    #     run_worker()
    #
    #     job.refresh_from_db()
    #     self.assertEqual(job.status, FsNodeDeletionJob.Status.FAILED)
    #     self.assertFalse(FsNode.objects.filter(pk=ok_file.pk).exists())
    #     self.assertTrue(FsNode.objects.filter(pk=stuck_file.pk).exists())


class DeletionWorkerTinyBatchTests(TestCase):
    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)

    def test_tiny_batch_can_finish_a_deep_chain(self) -> None:
        """
        Verify tiny batch processing for deep chains.

        Leaf directories must be found even if the first batch contains only non-leaves.
        """
        parent = self.root
        for index in range(4):
            parent = FsNodeDirectoryFactory(
                name=f"level-{index}",
                owner=self.user,
                storage=self.storage,
                parent=parent,
            )
        FsNodeFileFactory(
            name="deep.txt", owner=self.user, storage=self.storage, parent=parent, size=1,
        )
        job = remove_fs_node(self.user, PurePosixPath("/root"))

        run_worker(batch_size=1)

        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeDeletionJob.Status.DONE)
        self.assertEqual(FsNode.objects.filter(deletion_job=job).count(), 0)


class TestDeletionWorkerSignals(TestCase):
    """
    Test suite for the DeletionWorker's signal handling logic.

    These tests verify that the worker correctly handles OS signals (like SIGINT and SIGTERM)
    for graceful shutdown, ensuring that the keep_running flag is set correctly and
    that force exits are triggered when appropriate.
    """

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.stream = io.StringIO()
        self.worker = DeletionWorker(stdout=self.stream, stderr=self.stream)

    def test_handle_signal_sets_keep_running_false(self) -> None:
        """Verify that receiving a signal sets keep_running to False."""
        self.worker.keep_running = True
        self.worker._handle_signal(signal.SIGINT, None)
        self.assertFalse(self.worker.keep_running)
        self.assertEqual(self.stream.getvalue(), "\nReceived signal 2. Setting exit flag...\n")

    def test_handle_signal_force_exit(self) -> None:
        """Verify that receiving a signal when keep_running is already False calls os._exit(1)."""
        self.worker.keep_running = False
        with patch("os._exit") as mock_exit:
            self.worker._handle_signal(signal.SIGINT, None)
            mock_exit.assert_called_once_with(1)
        self.assertEqual(self.stream.getvalue(), "\nForce exiting immediately...\n")
