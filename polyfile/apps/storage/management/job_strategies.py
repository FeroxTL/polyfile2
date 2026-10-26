from abc import ABC, abstractmethod
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils.timezone import now

from polyfile.apps.storage.models import FsNodeDeletionJob


class JobClaimStrategy(ABC):
    @abstractmethod
    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeDeletionJob | None:
        """Abstract method to claim the next pending job from the database."""
        raise NotImplementedError


class RelationalClaimStrategy(JobClaimStrategy):
    """Strategy for PostgreSQL and MySQL (uses SELECT FOR UPDATE SKIP LOCKED)"""

    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeDeletionJob | None:
        """Claim a pending job from a relational database (PostgreSQL/MySQL) using SELECT FOR UPDATE SKIP LOCKED."""
        with transaction.atomic():
            # This is a standard high-performance way for queues in SQL
            job = (
                FsNodeDeletionJob.objects.select_for_update(skip_locked=True)
                .filter(status=FsNodeDeletionJob.Status.PENDING)
                .order_by("scheduled_at")
                .first()
            )

            if job:
                job.status = FsNodeDeletionJob.Status.RUNNING
                job.locked_by = hostname
                job.locked_until = now() + timedelta(seconds=lock_timeout)
                job.attempts += 1
                job.save(update_fields=("status", "locked_by", "locked_until", "attempts",))
                return job
            return None


class SQLiteClaimStrategy(JobClaimStrategy):
    """Strategy for SQLite (uses atomic update)"""

    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeDeletionJob | None:
        """Claim a pending job from an SQLite database using an atomic update."""
        # In SQLite, we cannot use skip_locked.
        # Therefore, we look for the job ID and then try to atomically update its status.
        # If another worker succeeded first, the number of updated rows will be 0.

        job_id = (
            FsNodeDeletionJob.objects.filter(status=FsNodeDeletionJob.Status.PENDING)
            .order_by("scheduled_at")
            .values("id")
            .first()
        )

        if job_id:
            updated_count = FsNodeDeletionJob.objects.filter(
                id=job_id["id"],
                status=FsNodeDeletionJob.Status.PENDING
            ).update(
                status=FsNodeDeletionJob.Status.RUNNING,
                locked_by=hostname,
                locked_until=now() + timedelta(seconds=lock_timeout),
                attempts=models.F("attempts") + 1,
            )

            if updated_count == 1:
                return FsNodeDeletionJob.objects.get(id=job_id["id"])

        return None


class JobStrategyFactory:
    """Factory for selecting the strategy based on DB settings"""

    @staticmethod
    def get_strategy() -> JobClaimStrategy:
        """Return the appropriate job claiming strategy based on the configured database engine."""
        engine = settings.DATABASES["default"]["ENGINE"]
        if engine in ("django.db.backends.sqlite3",):
            return SQLiteClaimStrategy()
        return RelationalClaimStrategy()
