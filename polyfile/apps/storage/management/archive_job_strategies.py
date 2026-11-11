"""Claim strategies for the directory archive worker."""

from abc import ABC, abstractmethod
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.utils.timezone import now

from polyfile.apps.storage.models import FsNodeArchiveJob


class ArchiveJobClaimStrategy(ABC):
    @abstractmethod
    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeArchiveJob | None:
        """Claim the next pending archive job."""
        raise NotImplementedError


class RelationalArchiveClaimStrategy(ArchiveJobClaimStrategy):
    """Claim strategy for PostgreSQL/MySQL using SELECT FOR UPDATE SKIP LOCKED."""

    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeArchiveJob | None:
        with transaction.atomic():
            job = (
                FsNodeArchiveJob.objects.select_for_update(skip_locked=True)
                .filter(
                    status=FsNodeArchiveJob.Status.PENDING,
                    scheduled_at__lte=now(),
                )
                .order_by("scheduled_at")
                .first()
            )
            if job is None:
                return None

            job.status = FsNodeArchiveJob.Status.RUNNING
            job.locked_by = hostname
            job.locked_until = now() + timedelta(seconds=lock_timeout)
            job.attempts += 1
            job.started_at = job.started_at or now()
            job.save(
                update_fields=(
                    "status",
                    "locked_by",
                    "locked_until",
                    "attempts",
                    "started_at",
                )
            )
            return job


class SQLiteArchiveClaimStrategy(ArchiveJobClaimStrategy):
    """Claim strategy for SQLite using a single atomic UPDATE."""

    def claim_job(self, hostname: str, lock_timeout: int) -> FsNodeArchiveJob | None:
        job_id = (
            FsNodeArchiveJob.objects.filter(
                status=FsNodeArchiveJob.Status.PENDING,
                scheduled_at__lte=now(),
            )
            .order_by("scheduled_at")
            .values("id")
            .first()
        )
        if job_id is None:
            return None

        updated_count = FsNodeArchiveJob.objects.filter(
            id=job_id["id"],
            status=FsNodeArchiveJob.Status.PENDING,
        ).update(
            status=FsNodeArchiveJob.Status.RUNNING,
            locked_by=hostname,
            locked_until=now() + timedelta(seconds=lock_timeout),
            attempts=models.F("attempts") + 1,
            started_at=models.functions.Coalesce(
                models.F("started_at"),
                models.Value(now()),
            ),
        )
        if updated_count != 1:
            return None
        return FsNodeArchiveJob.objects.get(id=job_id["id"])


class ArchiveStrategyFactory:
    """Select the claim strategy based on the configured database engine."""

    @staticmethod
    def get_strategy() -> ArchiveJobClaimStrategy:
        engine = settings.DATABASES["default"]["ENGINE"]
        if engine in ("django.db.backends.sqlite3",):
            return SQLiteArchiveClaimStrategy()
        return RelationalArchiveClaimStrategy()
