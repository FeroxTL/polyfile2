"""
Background worker for recursive deletion of FsNode subtrees.

This module provides a management command that processes `FsNodeDeletionJob`
objects. It handles the heavy lifting of deleting files and directories
recursively by prioritizing file deletion first, then iteratively removing
empty directories.

Deletion is row-first: database rows are removed together with an outbox
record for every physical object. The outbox is drained after commit, so a
crash between the DB and storage cannot leave an object without a retry key.

Key features:
- Stale job reanimation: Automatically recovers jobs that timed out or crashed.
- Concurrency safe: Uses `select_for_update(skip_locked=True)` for job claiming.
- Batch processing: Deletes nodes in chunks to optimize performance and resource usage.
- Archive protection: `FsNodeArchiveItem` uses `PROTECT`; a protected batch is
  rolled back and the job is rescheduled instead of failing terminally.
"""

import os
import signal
import socket
import time
from abc import ABC, abstractmethod
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import DatabaseError, models, transaction
from django.db.models.deletion import ProtectedError
from django.utils.timezone import now

from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.management.job_strategies import JobStrategyFactory
from polyfile.apps.storage.models import (
    FsNode,
    FsNodeDeletionJob,
    PendingObjectDeletion,
)


class JobClaimStrategy(ABC):
    @abstractmethod
    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeDeletionJob | None:
        pass


class DeletionWorker(BaseCommand):
    """
    Management command to run the deletion worker.

    This command continuously polls for `FsNodeDeletionJob` entries.
    It ensures that deletions are performed in a "leaf-first" manner:
    1. All file nodes associated with a job are deleted first.
    2. Empty directories (those with no children) are deleted in subsequent passes.

    This approach avoids deep recursion and allows for stable batching
    and error handling during large-scale deletions.
    """
    help = "Run background worker for recursive deletion of FsNode subtrees"

    PROTECTED_RETRY_DELAY = timedelta(seconds=60)

    def __init__(self, *args, lock_timeout: int = 300, max_attempts: int = 10, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.keep_running = True
        self.strategy = JobStrategyFactory.get_strategy()
        self.lock_timeout: int = lock_timeout
        self.max_attempts: int = max_attempts

    def add_arguments(self, parser) -> None:
        """Add command-line arguments to the parser."""
        parser.add_argument("--once", action="store_true", help="Run once and exit")
        parser.add_argument("--sleep", type=float, default=2.0, help="Sleep seconds when queue is empty")
        parser.add_argument("--batch-size", type=int, default=100, help="Number of nodes to process per batch")
        parser.add_argument("--lock-timeout", type=int, default=self.lock_timeout, help="Lock timeout in seconds")
        parser.add_argument("--max-attempts", type=int, default=self.max_attempts, help="Max attempts before marking FAILED")

    def _handle_signal(self, signum: int, frame) -> None:
        """Handle OS signals for graceful exit."""
        if not self.keep_running:
            self.stdout.write("\nForce exiting immediately...\n")
            return os._exit(1)

        self.stdout.write(f"\nReceived signal {signum}. Setting exit flag...\n")
        self.keep_running = False

    def handle(self, *args, **options):
        """Main entry point for the command. Orchestrates the job processing loop."""
        once = options["once"]
        sleep_seconds = options["sleep"]
        batch_size = options["batch_size"]
        self.lock_timeout = options["lock_timeout"]
        self.max_attempts = options["max_attempts"]
        worker_id = f"{socket.gethostname()}:{os.getpid()}"

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.stdout.write(self.style.SUCCESS("Starting deletion worker..."))

        while self.keep_running:
            self._reanimate_stale_jobs()
            self._process_outbox(batch_size)
            job = self._claim_job(worker_id)
            if job is None:
                if once:
                    break
                time.sleep(sleep_seconds)
                continue
            try:
                self._process_job(job, batch_size)
            except ProtectedError as exc:
                # An archive manifest still references this node. Roll back the
                # whole batch and retry later; this is not a terminal failure.
                self._reschedule_protected_job(job, exc)
            except (OSError, DatabaseError, TimeoutError) as exc:
                # Handle expected operational errors (disk, DB, timeouts)
                # Mark the job as failed and continue to the next one
                self._fail_job(job, exc)
            except Exception as exc:  # noqa: BLE001
                # Handle unexpected logic errors (bugs)
                self.stdout.write(self.style.ERROR(f"Unexpected error occurred: {exc}"))
                self._fail_job(job, exc)
            # A job may have produced outbox rows. Drain them before --once exits.
            self._process_outbox(batch_size)
            if once:
                break

    def _reanimate_stale_jobs(self) -> None:
        """Identify and reset jobs that have been timed out or reached max attempts."""
        current_time = now()
        stale_jobs = FsNodeDeletionJob.objects.filter(
            models.Q(locked_until__lte=current_time) | models.Q(locked_until__isnull=True),
            status=FsNodeDeletionJob.Status.RUNNING,
        )

        # 1. Update jobs that have exceeded the maximum number of attempts.
        # These jobs are considered failed and should be marked as TIMEOUT.
        stale_jobs.filter(attempts__gte=self.max_attempts).update(
            status=FsNodeDeletionJob.Status.TIMEOUT,
            finished_at=current_time,
            locked_until=None,
            locked_by="",
        )

        # 2. Update jobs that are just "stale" but haven't reached max attempts
        # These jobs should be returned to the pending queue.
        # This performs a second SQL query for all matching records.
        stale_jobs.filter(attempts__lt=self.max_attempts).update(
            status=FsNodeDeletionJob.Status.PENDING,
            locked_until=None,
            locked_by="",
        )

    def _claim_job(self, worker_id: str) -> FsNodeDeletionJob | None:
        """Claim the next pending deletion job from the database using the selected strategy."""
        return self.strategy.claim_job(worker_id, self.lock_timeout)

    def _process_job(self, job: FsNodeDeletionJob, batch_size: int) -> None:
        """Execute the deletion logic for a specific job in batches."""
        if job.attempts > self.max_attempts:
            self._fail_job(job, Exception("Max attempts exceeded"))
            return

        # Update totals if not set
        if job.total_nodes == 0:
            job.total_nodes = FsNode.objects.filter(deletion_job=job).count()
            job.save(update_fields=("total_nodes",))

        # Process in batches: delete files first, then empty directories (leaf-first)
        while True:
            # 1) Delete file nodes (definitely leaves)
            file_nodes = list(
                FsNode.objects.filter(deletion_job=job, type=FsNode.TypeChoices.FILE)
                .order_by("pk")[:batch_size]
            )
            if file_nodes:
                self._delete_file_nodes(file_nodes)
                # processed_nodes tracks attempted deletions in this pass, not
                # successful ones. Failed files stay in the job and are retried.
                job.processed_nodes += len(file_nodes)
                job.save(update_fields=("processed_nodes",))

            # 2) Delete empty directories (no children in objects - also leaves)
            if not (processed := bool(file_nodes)):
                dir_pks = list(
                    FsNode.objects.filter(
                        deletion_job=job,
                        type=FsNode.TypeChoices.DIRECTORY,
                    )
                    .annotate(
                        has_children=models.Exists(
                            FsNode.objects.filter(parent_id=models.OuterRef("pk"))
                        )
                    )
                    .filter(has_children=False)
                    .order_by("pk")
                    .values_list("pk", flat=True)[:batch_size]
                )
                if dir_pks:
                    deleted_count, _ = FsNode.objects.filter(pk__in=dir_pks).delete()
                    job.processed_nodes += deleted_count
                    job.save(update_fields=("processed_nodes",))
                    processed = True

            if not processed:
                break

        remaining = FsNode.objects.filter(deletion_job=job).count()
        if remaining == 0:
            job.status = FsNodeDeletionJob.Status.DONE
            job.finished_at = now()
            job.locked_until = None
            job.save(update_fields=("status", "finished_at", "locked_until",))
            self.stdout.write(self.style.SUCCESS(f"Job {job.pk} completed"))
        else:
            # Extend lock and continue later
            job.locked_until = now() + timedelta(seconds=self.lock_timeout)
            job.save(update_fields=("locked_until",))

    @staticmethod
    def _delete_file_nodes(file_nodes: list[FsNode]) -> None:
        """
        Delete file rows and enqueue their physical objects in one transaction.

        The outbox row is the durable retry key. It is committed only if the
        whole `FsNode` batch is deleted, so `PROTECT` from an archive manifest
        rolls back both the rows and the outbox.
        """
        with transaction.atomic():
            outbox = []
            for node in file_nodes:
                ref = node.storage_object
                if ref is None:
                    continue
                outbox.append(
                    PendingObjectDeletion(
                        storage_id=ref.storage_id,
                        object_key=ref.key,
                        node_uuid=node.pk,
                    )
                )
            if outbox:
                PendingObjectDeletion.objects.bulk_create(outbox, ignore_conflicts=True)

            # Use queryset delete to avoid FsNode.delete(), which would try to
            # remove the storage object a second time.
            FsNode.objects.filter(pk__in=[node.pk for node in file_nodes]).delete()

    def _process_outbox(self, batch_size: int) -> None:
        """Delete physical objects whose DB rows have already been removed."""
        rows = list(
            PendingObjectDeletion.objects.order_by("created_at", "pk")[:batch_size]
        )
        if not rows:
            return

        by_storage: dict[int, list[PendingObjectDeletion]] = {}
        for row in rows:
            by_storage.setdefault(row.storage_id, []).append(row)

        successful_ids: list[int] = []
        for storage_id, entries in by_storage.items():
            try:
                storage = fs_storages[storage_id]
            except Exception as exc:  # noqa: BLE001 - backend initialization can raise arbitrary errors
                self._mark_outbox_failure(entries, exc)
                continue

            names = [entry.storage_object.key for entry in entries]
            try:
                results = storage.delete_many(names)
            except Exception as exc:  # noqa: BLE001 - collect backend errors and retry
                self._mark_outbox_failure(entries, exc)
                continue

            for entry in entries:
                result = results.get(entry.storage_object.key)
                if result is True:
                    successful_ids.append(entry.pk)
                else:
                    self._mark_outbox_failure(
                        [entry],
                        result if isinstance(result, Exception) else OSError(
                            f"Storage did not delete "
                            f"{entry.storage_object.key!r}: {result!r}"
                        ),
                    )

        if successful_ids:
            PendingObjectDeletion.objects.filter(pk__in=successful_ids).delete()

    @staticmethod
    def _mark_outbox_failure(
        entries: list[PendingObjectDeletion],
        exc: Exception,
    ) -> None:
        message = str(exc)[:4000]
        for entry in entries:
            entry.attempts += 1
            entry.last_error = message
            entry.save(update_fields=("attempts", "last_error"))

    def _reschedule_protected_job(self, job: FsNodeDeletionJob, exc: ProtectedError) -> None:
        """Retry a job later when an archive manifest still protects its nodes."""
        job.status = FsNodeDeletionJob.Status.PENDING
        # The claim already incremented attempts; protection is not a failed try.
        job.attempts = max(0, job.attempts - 1)
        job.scheduled_at = now() + self.PROTECTED_RETRY_DELAY
        job.locked_until = None
        job.locked_by = ""
        job.last_error = str(exc)[:4000]
        job.save(
            update_fields=(
                "status",
                "attempts",
                "scheduled_at",
                "locked_until",
                "locked_by",
                "last_error",
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"Job {job.pk} is protected by an archive manifest; retry scheduled"
            )
        )

    def _fail_job(self, job: FsNodeDeletionJob, exc: Exception) -> None:
        """Handle job failure. Database errors are retried, other errors are terminal."""
        job.last_error = str(exc)[:4000]
        job.locked_until = None
        job.locked_by = ""

        if isinstance(exc, DatabaseError) and job.attempts < self.max_attempts:
            job.status = FsNodeDeletionJob.Status.PENDING
            job.save(update_fields=("status", "last_error", "locked_until", "locked_by"))
            self.stdout.write(self.style.WARNING(f"Job {job.pk} will be retried due to database error: {exc}"))
            return

        job.status = FsNodeDeletionJob.Status.TIMEOUT if isinstance(exc, DatabaseError) else FsNodeDeletionJob.Status.FAILED
        job.finished_at = now()
        job.save(update_fields=("status", "finished_at", "last_error", "locked_until", "locked_by"))
        self.stdout.write(self.style.ERROR(f"Job {job.pk} failed: {exc}"))


Command = DeletionWorker
