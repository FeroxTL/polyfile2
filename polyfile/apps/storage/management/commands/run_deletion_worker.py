"""
Background worker for recursive deletion of FsNode subtrees.

This module provides a management command that processes `FsNodeDeletionJob`
objects. It handles the heavy lifting of deleting files and directories
recursively by prioritizing file deletion first, then iteratively removing
empty directories.

Key features:
- Stale job reanimation: Automatically recovers jobs that timed out or crashed.
- Concurrency safe: Uses `select_for_update(skip_locked=True)` for job claiming.
- Batch processing: Deletes nodes in chunks to optimize performance and resource usage.
"""

import os
import signal
import socket
import time
from abc import ABC, abstractmethod
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import DatabaseError, models
from django.utils.timezone import now

from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.management.job_strategies import JobStrategyFactory
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob


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
            job = self._claim_job(worker_id)
            if job is None:
                if once:
                    break
                time.sleep(sleep_seconds)
                continue
            try:
                self._process_job(job, batch_size)
            except (OSError, DatabaseError, TimeoutError) as exc:
                # Handle expected operational errors (disk, DB, timeouts)
                # Mark the job as failed and continue to the next one
                self._fail_job(job, exc)
            except Exception as exc:  # noqa: BLE001
                # Handle unexpected logic errors (bugs)
                self.stdout.write(self.style.ERROR(f"Unexpected error occurred: {exc}"))
                self._fail_job(job, exc)
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
        Delete file nodes from storage and database.

        Storage deletion is attempted first. Database rows are removed only for
        nodes whose storage deletion succeeded. If any file cannot be removed
        from storage, the remaining tombstones are kept and the caller receives
        an error so the job is not reported as completed.
        """
        by_storage = {}
        for node in file_nodes:
            by_storage.setdefault(node.storage_id, []).append(node)

        deleted_nodes = []
        failures = []

        for storage_id, nodes in by_storage.items():
            nodes_with_files = [n for n in nodes if n.file and n.file.name]
            deleted_nodes.extend(n for n in nodes if not (n.file and n.file.name))
            if not nodes_with_files:
                continue

            try:
                storage = fs_storages[storage_id]
            except Exception as exc:  # noqa: BLE001 - backend initialization can raise arbitrary errors
                failures.append(f"storage {storage_id}: {exc}")
                continue

            names = [n.file.name for n in nodes_with_files]
            try:
                results = storage.delete_many(names)
            except Exception as exc:  # noqa: BLE001 - collect backend errors and report them
                failures.extend(f"{name!r}: {exc}" for name in names)
                continue
            for node in nodes_with_files:
                result = results.get(node.file.name)
                if result is True:
                    deleted_nodes.append(node)
                else:
                    failures.append(f"{node.file.name!r}: {result}")

        # Delete DB rows only for files that were successfully removed from storage.
        # Use a queryset delete to avoid FsNode.delete(), which would try to remove
        # the already deleted storage object a second time.
        pks = [node.pk for node in deleted_nodes]
        if pks:
            FsNode.objects.filter(pk__in=pks).delete()

        if failures:
            preview = "; ".join(failures[:5])
            if len(failures) > 5:
                preview += f"; ... and {len(failures) - 5} more"
            raise OSError(f"Failed to delete {len(failures)} file(s) from storage: {preview}")

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
