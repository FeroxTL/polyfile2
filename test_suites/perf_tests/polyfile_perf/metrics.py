"""Request and resource metrics collected during a harness run."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Self

import psutil


@dataclass(frozen=True)
class RequestSample:
    """One HTTP request performed by the harness."""

    timestamp: float
    method: str
    path: str
    status_code: int
    elapsed_ms: float

    @property
    def ok(self) -> bool:
        """Return whether the request completed with a 2xx/3xx status."""
        return 200 <= self.status_code < 400


@dataclass(frozen=True)
class ResourceSample:
    """A point-in-time sample of machine resource usage."""

    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_bytes: int
    disk_read_bytes: int
    disk_write_bytes: int


def percentile(values: list[float], ratio: float) -> float:
    """Return a simple nearest-rank percentile for a non-empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(ratio * (len(ordered) - 1))))
    return ordered[index]


class RequestRecorder:
    """Thread-safe collector of :class:`RequestSample` values."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: list[RequestSample] = []

    def record(self, sample: RequestSample) -> None:
        """Append a sample; safe to call from worker threads."""
        with self._lock:
            self._samples.append(sample)

    @property
    def samples(self) -> list[RequestSample]:
        """Return a snapshot of the recorded samples."""
        with self._lock:
            return list(self._samples)

    def clear(self) -> None:
        """Drop all recorded samples."""
        with self._lock:
            self._samples.clear()

    def summary(self, duration_seconds: float) -> dict[str, Any]:
        """Return aggregate counts and latency percentiles."""
        samples = self.samples
        latencies = [sample.elapsed_ms for sample in samples]
        errors = [sample for sample in samples if not sample.ok]
        status_counts: dict[str, int] = {}
        for sample in samples:
            key = str(sample.status_code)
            status_counts[key] = status_counts.get(key, 0) + 1

        return {
            "requests": len(samples),
            "errors": len(errors),
            "error_rate": (len(errors) / len(samples)) if samples else 0.0,
            "requests_per_second": (len(samples) / duration_seconds) if duration_seconds else 0.0,
            "latency_ms": {
                "mean": (sum(latencies) / len(latencies)) if latencies else 0.0,
                "p50": percentile(latencies, 0.50),
                "p90": percentile(latencies, 0.90),
                "p95": percentile(latencies, 0.95),
                "p99": percentile(latencies, 0.99),
                "max": max(latencies) if latencies else 0.0,
            },
            "status_counts": status_counts,
        }


class ResourceSampler:
    """Background sampler of CPU, memory and disk I/O counters."""

    def __init__(self, interval: float = 1.0) -> None:
        self._interval = max(0.1, interval)
        self._samples: list[ResourceSample] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def samples(self) -> list[ResourceSample]:
        """Return a snapshot of collected resource samples."""
        with self._lock:
            return list(self._samples)

    def start(self) -> None:
        """Start sampling in a daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        psutil.cpu_percent(interval=None)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="perf-resource-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop sampling and wait for the thread to finish."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 2)
            self._thread = None

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                sample = self.sample()
            except (psutil.Error, OSError):
                continue
            with self._lock:
                self._samples.append(sample)

    @staticmethod
    def sample() -> ResourceSample:
        """Take a single resource sample."""
        memory = psutil.virtual_memory()
        try:
            disk = psutil.disk_io_counters()
        except (psutil.Error, OSError):
            disk = None
        return ResourceSample(
            timestamp=time.time(),
            cpu_percent=psutil.cpu_percent(interval=None),
            memory_percent=memory.percent,
            memory_used_bytes=memory.used,
            disk_read_bytes=disk.read_bytes if disk else 0,
            disk_write_bytes=disk.write_bytes if disk else 0,
        )
