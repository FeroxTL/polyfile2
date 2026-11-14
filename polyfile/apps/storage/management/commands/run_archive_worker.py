"""Background worker that builds directory ZIP archives from manifests.

The worker never walks the live tree. It reads only ``FsNodeArchiveItem`` rows,
so the archive is a true snapshot of the moment the job was requested. The ZIP
is written to a temporary ``.part`` file and published atomically; a partial
archive is never visible to readers.
"""

import hashlib
import logging
import os
import shutil
import signal
import socket
import time
import zipfile
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import DatabaseError, models, transaction
from django.utils.timezone import now

from polyfile.apps.storage.archive_backend import get_archive_backend
from polyfile.apps.storage.management.archive_job_strategies import (
    ArchiveStrategyFactory,
)
from polyfile.apps.storage.models import FsNodeArchiveItem, FsNodeArchiveJob

logger = logging.getLogger(__name__)


class ArchiveCancelled(Exception):
    """Raised internally when a job is cancelled while being built."""


class ArchiveSourceMissing(Exception):
    """Raised when a snapshotted source file vanished before the build.

    The message intentionally references only the path inside the ZIP:
    absolute server paths must never reach the client.
    """

    def __init__(self, zip_path: str) -> None:
        self.zip_path = zip_path
        super().__init__(f'Archive source file is missing: "{zip_path}"')


class ArchiveWorker(BaseCommand):
    """Management command that builds pending directory archives."""

    help = "Run background worker for directory archive jobs"

    RETRY_BASE_DELAY = timedelta(seconds=30)
    RETRY_MAX_DELAY = timedelta(seconds=300)

    def __init__(
        self,
        *args,
        lock_timeout: int = 300,
        max_attempts: int = 3,
        progress_interval: int = 100,
        cancel_check_interval: int = 100,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.keep_running = True
        self.strategy = ArchiveStrategyFactory.get_strategy()
        self.lock_timeout = lock_timeout
        self.max_attempts = max_attempts
        self.progress_interval = max(1, progress_interval)
        self.cancel_check_interval = max(1, cancel_check_interval)

    def add_arguments(self, parser) -> None:
        parser.add_argument("--once", action="store_true", help="Run once and exit")
        parser.add_argument("--sleep", type=float, default=2.0, help="Sleep seconds when the queue is empty")
        parser.add_argument("--lock-timeout", type=int, default=self.lock_timeout, help="Lock timeout in seconds")
        parser.add_argument("--max-attempts", type=int, default=self.max_attempts, help="Max attempts before marking FAILED")
        parser.add_argument("--progress-interval", type=int, default=self.progress_interval, help="Entries between progress updates")
        parser.add_argument("--cancel-check-interval", type=int, default=self.cancel_check_interval, help="Entries between cancellation checks")

    def _handle_signal(self, signum: int, frame) -> None:
        if not self.keep_running:
            self.stdout.write("\nForce exiting immediately...\n")
            return os._exit(1)
        self.stdout.write(f"\nReceived signal {signum}. Setting exit flag...\n")
        self.keep_running = False

    def handle(self, *args, **options):
        once = options["once"]
        sleep_seconds = options["sleep"]
        self.lock_timeout = options["lock_timeout"]
        self.max_attempts = options["max_attempts"]
        self.progress_interval = max(1, options["progress_interval"])
        self.cancel_check_interval = max(1, options["cancel_check_interval"])
        worker_id = f"{socket.gethostname()}:{os.getpid()}"

        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.stdout.write(self.style.SUCCESS("Starting archive worker..."))

        while self.keep_running:
            self._reanimate_stale_jobs()
            job = self._claim_job(worker_id)
            if job is None:
                if once:
                    break
                time.sleep(sleep_seconds)
                continue

            try:
                self._process_job(job)
            except Exception as exc:
                logger.exception("Unexpected archive worker error for job %s", job.pk)
                self._fail_job(job, exc, retry=False)

            if once:
                break

    def _claim_job(self, worker_id: str) -> FsNodeArchiveJob | None:
        return self.strategy.claim_job(worker_id, self.lock_timeout)

    def _reanimate_stale_jobs(self) -> None:
        """Return timed-out jobs to the queue or fail them after max attempts."""
        current_time = now()
        stale = FsNodeArchiveJob.objects.filter(
            status=FsNodeArchiveJob.Status.RUNNING,
        ).filter(
            models.Q(locked_until__lte=current_time) | models.Q(locked_until__isnull=True)
        )

        failed_ids = list(
            stale.filter(attempts__gte=self.max_attempts).values_list("pk", flat=True)
        )
        if failed_ids:
            with transaction.atomic():
                FsNodeArchiveJob.objects.filter(pk__in=failed_ids).update(
                    status=FsNodeArchiveJob.Status.FAILED,
                    finished_at=current_time,
                    locked_until=None,
                    locked_by="",
                    last_error="Archive worker timed out.",
                )
                FsNodeArchiveItem.objects.filter(job_id__in=failed_ids).delete()
            logger.warning(
                "Marked %s stale archive job(s) as failed after max attempts: %s",
                len(failed_ids),
                ", ".join(str(pk) for pk in failed_ids),
            )
            self.stdout.write(
                self.style.ERROR(
                    f"Marked {len(failed_ids)} stale archive job(s) as failed: "
                    f"{', '.join(str(pk) for pk in failed_ids)}"
                )
            )

        requeued = stale.filter(attempts__lt=self.max_attempts).update(
            status=FsNodeArchiveJob.Status.PENDING,
            locked_until=None,
            locked_by="",
        )
        if requeued:
            logger.info("Requeued %s stale archive job(s)", requeued)
            self.stdout.write(
                self.style.WARNING(f"Requeued {requeued} stale archive job(s)")
            )

    def _job_label(self, job: FsNodeArchiveJob) -> str:
        """Return a compact, consistent description of a job for logs."""
        return (
            f"job={job.pk} root={job.root_node_name!r} "
            f"files={job.total_files} bytes={job.total_bytes} "
            f"attempt={job.attempts}/{self.max_attempts}"
        )

    def _process_job(self, job: FsNodeArchiveJob) -> None:
        if job.attempts > self.max_attempts:
            self._fail_job(job, Exception("Max attempts exceeded"), retry=False)
            return

        backend = get_archive_backend()
        key = self._archive_key(job)

        logger.info(
            "Building archive %s",
            self._job_label(job),
        )
        self.stdout.write(f"Building archive {self._job_label(job)}")

        try:
            self._check_cancelled(job)
            with backend.open_for_write(key) as raw_file, zipfile.ZipFile(
                raw_file,
                "w",
                zipfile.ZIP_STORED,
                allowZip64=True,
            ) as archive:
                self._write_manifest(job, archive)

            archive_size = backend.size(key)
            archive_md5 = self._md5(backend, key)
            self._mark_ready(job, key, archive_size, archive_md5)
        except ArchiveCancelled:
            self._delete_archive_safely(backend, key)
            self._mark_cancelled(job)
        except ArchiveSourceMissing as exc:
            # A snapshotted object disappeared. Retrying cannot fix the
            # snapshot; the client can request a new one.
            self._delete_archive_safely(backend, key)
            self._fail_job(job, exc, retry=False)
        except FileNotFoundError as exc:
            # A snapshotted object disappeared. Retrying cannot fix the
            # snapshot; the client can request a new one.
            self._delete_archive_safely(backend, key)
            self._fail_job(job, exc, retry=False)
        except (OSError, DatabaseError, TimeoutError, zipfile.BadZipFile) as exc:
            self._delete_archive_safely(backend, key)
            self._fail_job(job, exc, retry=True)
        except Exception as exc:  # noqa: BLE001 - report unexpected errors as terminal
            self._delete_archive_safely(backend, key)
            self._fail_job(job, exc, retry=False)

    def _write_manifest(self, job: FsNodeArchiveJob, archive: zipfile.ZipFile) -> None:
        processed_files = 0
        processed_bytes = 0

        items = job.items.order_by("position").iterator(chunk_size=1000)
        for index, item in enumerate(items, start=1):
            if index % self.cancel_check_interval == 0:
                self._check_cancelled(job)

            if item.entry_type == FsNodeArchiveItem.EntryType.DIRECTORY:
                info = zipfile.ZipInfo(item.zip_path)
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (0o40755 << 16) | 0x10
                archive.writestr(info, b"")
            elif not item.file:
                # A file node that was created but never uploaded is still an
                # empty file in the snapshot.
                archive.writestr(item.zip_path, b"")
                processed_files += 1
            else:
                # Use the manifest snapshot, not item.node.file: the node may
                # have been re-uploaded or moved to another storage after the
                # job was requested.
                try:
                    source = item.file.open("rb")
                except FileNotFoundError:
                    raise ArchiveSourceMissing(item.zip_path) from None
                with source, archive.open(
                    item.zip_path,
                    "w",
                ) as target:
                    shutil.copyfileobj(source, target, length=1024 * 1024)
                processed_files += 1
                processed_bytes += item.size

            if index % self.progress_interval == 0:
                self._update_progress(job, processed_files, processed_bytes)
                logger.info(
                    "Archive job %s progress: %s/%s files, %s/%s bytes",
                    job.pk,
                    processed_files,
                    job.total_files,
                    processed_bytes,
                    job.total_bytes,
                )

        self._update_progress(job, processed_files, processed_bytes)
        logger.info(
            "Archive job %s manifest written: %s files, %s bytes",
            job.pk,
            processed_files,
            processed_bytes,
        )

    def _check_cancelled(self, job: FsNodeArchiveJob) -> None:
        state = (
            FsNodeArchiveJob.objects.filter(pk=job.pk)
            .values("status", "cancel_requested")
            .first()
        )
        if (
            state is None
            or state["status"] != FsNodeArchiveJob.Status.RUNNING
            or state["cancel_requested"]
        ):
            raise ArchiveCancelled

    def _update_progress(
        self,
        job: FsNodeArchiveJob,
        processed_files: int,
        processed_bytes: int,
    ) -> None:
        locked_until = now() + timedelta(seconds=self.lock_timeout)
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            processed_files=processed_files,
            processed_bytes=processed_bytes,
            locked_until=locked_until,
        )
        job.processed_files = processed_files
        job.processed_bytes = processed_bytes
        job.locked_until = locked_until

    def _mark_ready(
        self,
        job: FsNodeArchiveJob,
        key: str,
        archive_size: int,
        archive_md5: str,
    ) -> None:
        ttl = getattr(settings, "DIRECTORY_ARCHIVE_TTL", timedelta(hours=24))
        with transaction.atomic():
            locked = FsNodeArchiveJob.objects.select_for_update().get(pk=job.pk)
            if (
                locked.status != FsNodeArchiveJob.Status.RUNNING
                or locked.cancel_requested
            ):
                raise ArchiveCancelled

            finished_at = now()
            locked.status = FsNodeArchiveJob.Status.READY
            locked.archive_key = key
            locked.archive_size = archive_size
            locked.archive_md5 = archive_md5
            locked.processed_files = locked.total_files
            locked.processed_bytes = locked.total_bytes
            locked.finished_at = finished_at
            locked.expires_at = finished_at + ttl
            locked.locked_until = None
            locked.locked_by = ""
            locked.last_error = ""
            locked.save(
                update_fields=(
                    "status",
                    "archive_key",
                    "archive_size",
                    "archive_md5",
                    "processed_files",
                    "processed_bytes",
                    "finished_at",
                    "expires_at",
                    "locked_until",
                    "locked_by",
                    "last_error",
                )
            )
            # The manifest is no longer needed once the archive is independent.
            locked.items.all().delete()

        logger.info(
            "Archive job %s ready: key=%s size=%s md5=%s expires_at=%s",
            job.pk,
            key,
            archive_size,
            archive_md5,
            locked.expires_at.isoformat(),
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Archive job {job.pk} ready: {archive_size} bytes -> {key}"
            )
        )

    def _mark_cancelled(self, job: FsNodeArchiveJob) -> None:
        with transaction.atomic():
            FsNodeArchiveJob.objects.filter(pk=job.pk).update(
                status=FsNodeArchiveJob.Status.CANCELLED,
                cancel_requested=True,
                finished_at=now(),
                locked_until=None,
                locked_by="",
                last_error="Archive cancelled.",
            )
            FsNodeArchiveItem.objects.filter(job_id=job.pk).delete()

        logger.info("Archive job %s cancelled", job.pk)
        self.stdout.write(self.style.WARNING(f"Archive job {job.pk} cancelled"))

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        """Return a message safe to expose via the API.

        ``str(OSError)`` embeds the absolute filename, which would leak server
        paths to the client; ``exc.strerror`` carries the same diagnostic
        without the path. Full details are still written to the server log by
        the caller.
        """
        if isinstance(exc, OSError) and exc.strerror:
            return exc.strerror[:4000]
        return str(exc)[:4000]

    def _fail_job(
        self,
        job: FsNodeArchiveJob,
        exc: Exception,
        retry: bool,
    ) -> None:
        message = self._safe_error_message(exc)
        job.last_error = message

        if retry and job.attempts < self.max_attempts:
            job.status = FsNodeArchiveJob.Status.PENDING
            job.scheduled_at = now() + self._retry_delay(job.attempts)
            job.locked_until = None
            job.locked_by = ""
            job.save(
                update_fields=(
                    "status",
                    "scheduled_at",
                    "last_error",
                    "locked_until",
                    "locked_by",
                )
            )
            logger.warning(
                "Archive job %s will be retried at %s: %s",
                job.pk,
                job.scheduled_at.isoformat(),
                exc,
            )
            self.stdout.write(
                self.style.WARNING(
                    f"Job {job.pk} will be retried: {exc}"
                )
            )
            return

        with transaction.atomic():
            job.status = FsNodeArchiveJob.Status.FAILED
            job.finished_at = now()
            job.locked_until = None
            job.locked_by = ""
            job.save(
                update_fields=(
                    "status",
                    "finished_at",
                    "last_error",
                    "locked_until",
                    "locked_by",
                )
            )
            FsNodeArchiveItem.objects.filter(job_id=job.pk).delete()
        logger.error(
            "Archive job %s failed permanently: %s",
            job.pk,
            exc,
        )
        self.stdout.write(self.style.ERROR(f"Job {job.pk} failed: {exc}"))

    def _retry_delay(self, attempts: int) -> timedelta:
        exponent = max(0, attempts - 1)
        return min(self.RETRY_BASE_DELAY * (2 ** exponent), self.RETRY_MAX_DELAY)

    @staticmethod
    def _archive_key(job: FsNodeArchiveJob) -> str:
        job_id = str(job.pk)
        return f"archives/{job_id[:2]}/{job_id}.zip"

    @staticmethod
    def _md5(backend, key: str) -> str:
        digest = hashlib.md5()
        with backend.open(key) as fileobj:
            for chunk in iter(lambda: fileobj.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _delete_archive_safely(backend, key: str) -> None:
        try:
            backend.delete(key)
        except OSError:
            logger.exception("Failed to delete partial archive %s", key)


Command = ArchiveWorker
