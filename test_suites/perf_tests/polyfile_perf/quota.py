"""Disk-usage observation and quota enforcement.

The load harness creates and deletes files, and archive jobs write ZIPs. This
module only *observes* directory sizes; it never removes data. When a limit is
crossed the run is aborted so a misconfigured test cannot fill the disk.
"""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import psutil

from polyfile_perf.config import QuotaConfig


class QuotaExceeded(RuntimeError):
    """Raised when a configured disk quota is exceeded."""

    def __init__(self, violations: list[str], snapshot: UsageSnapshot) -> None:
        self.violations = violations
        self.snapshot = snapshot
        super().__init__("; ".join(violations))


@dataclass(frozen=True)
class UsageSnapshot:
    """A single observation of the watched directories."""

    timestamp: float
    temp_bytes: int
    archive_bytes: int
    total_bytes: int
    free_bytes: int
    temp_limit: int
    archive_limit: int
    total_limit: int
    min_free: int

    @property
    def violations(self) -> list[str]:
        """Return human-readable descriptions of exceeded limits."""
        problems: list[str] = []
        if self.temp_bytes > self.temp_limit:
            problems.append(
                f"temp usage {format_bytes(self.temp_bytes)} exceeds "
                f"limit {format_bytes(self.temp_limit)}"
            )
        if self.archive_bytes > self.archive_limit:
            problems.append(
                f"archive usage {format_bytes(self.archive_bytes)} exceeds "
                f"limit {format_bytes(self.archive_limit)}"
            )
        if self.total_bytes > self.total_limit:
            problems.append(
                f"total data usage {format_bytes(self.total_bytes)} exceeds "
                f"limit {format_bytes(self.total_limit)}"
            )
        if self.free_bytes < self.min_free:
            problems.append(
                f"free disk space {format_bytes(self.free_bytes)} is below "
                f"reserve {format_bytes(self.min_free)}"
            )
        return problems

    @property
    def ok(self) -> bool:
        """Return whether every configured limit is satisfied."""
        return not self.violations


def format_bytes(value: int) -> str:
    """Format a byte count with binary units."""
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024.0 or unit == "TiB":
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TiB"


def directory_size(path: Path) -> int:
    """Return the recursive size of ``path`` in bytes; missing paths are 0."""
    total = 0
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat(follow_symlinks=False).st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += directory_size(Path(entry.path))
                except FileNotFoundError:
                    # A concurrent deletion/rename is expected during load tests.
                    continue
    except FileNotFoundError:
        return 0
    except NotADirectoryError:
        try:
            return path.stat().st_size
        except FileNotFoundError:
            return 0
    return total


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists():
        if current.parent == current:
            return Path.cwd()
        current = current.parent
    return current


class QuotaMonitor:
    """Observe configured directories and abort when limits are exceeded."""

    def __init__(
        self,
        config: QuotaConfig,
        *,
        disk_usage: Callable[[str], psutil._common.sdiskusage] = psutil.disk_usage,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._disk_usage = disk_usage
        self._clock = clock
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def config(self) -> QuotaConfig:
        """Return the active quota configuration."""
        return self._config

    def snapshot(self) -> UsageSnapshot:
        """Measure the watched directories and free disk space."""
        data_dir = self._config.resolved_data_dir()
        temp_dir = self._config.resolved_temp_dir()
        archive_dir = self._config.resolved_archive_dir()

        temp_bytes = directory_size(temp_dir)
        archive_bytes = directory_size(archive_dir)
        total_bytes = directory_size(data_dir)
        try:
            free_bytes = self._disk_usage(str(_existing_ancestor(data_dir))).free
        except OSError:
            free_bytes = 0

        return UsageSnapshot(
            timestamp=self._clock(),
            temp_bytes=temp_bytes,
            archive_bytes=archive_bytes,
            total_bytes=total_bytes,
            free_bytes=free_bytes,
            temp_limit=self._config.max_temp_bytes,
            archive_limit=self._config.max_archive_bytes,
            total_limit=self._config.max_total_bytes,
            min_free=self._config.min_free_bytes,
        )

    def enforce(self) -> UsageSnapshot:
        """Return a snapshot or raise :class:`QuotaExceeded`."""
        snapshot = self.snapshot()
        if self._config.enabled and not snapshot.ok:
            raise QuotaExceeded(snapshot.violations, snapshot)
        return snapshot

    def start(self, on_exceeded: Callable[[QuotaExceeded], None] | None = None) -> None:
        """Start a background guard that enforces quotas periodically."""
        if not self._config.enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(on_exceeded,),
            name="perf-quota-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background guard."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._config.poll_interval * 2)
            self._thread = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def _run(self, on_exceeded: Callable[[QuotaExceeded], None] | None) -> None:
        while not self._stop.wait(self._config.poll_interval):
            try:
                self.enforce()
            except QuotaExceeded as exc:
                if on_exceeded is not None:
                    on_exceeded(exc)
                self._stop.set()
                return
