from __future__ import annotations

from pathlib import Path

import pytest

from polyfile_perf.config import QuotaConfig
from polyfile_perf.quota import (
    QuotaExceeded,
    QuotaMonitor,
    UsageSnapshot,
    directory_size,
    format_bytes,
)


def test_directory_size_is_recursive(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.bin").write_bytes(b"x" * 10)
    (tmp_path / "two.bin").write_bytes(b"y" * 5)

    assert directory_size(tmp_path) == 15


def test_directory_size_missing_path_is_zero(tmp_path: Path) -> None:
    assert directory_size(tmp_path / "missing") == 0


def test_format_bytes() -> None:
    assert format_bytes(0) == "0.0 B"
    assert format_bytes(1024) == "1.0 KiB"
    assert format_bytes(1024**2) == "1.0 MiB"


def make_snapshot(**overrides: int) -> UsageSnapshot:
    values = {
        "timestamp": 0.0,
        "temp_bytes": 0,
        "archive_bytes": 0,
        "total_bytes": 0,
        "free_bytes": 10**12,
        "temp_limit": 10,
        "archive_limit": 10,
        "total_limit": 10,
        "min_free": 0,
    }
    values.update(overrides)
    return UsageSnapshot(**values)


def test_snapshot_reports_violations() -> None:
    snapshot = make_snapshot(
        temp_bytes=11,
        archive_bytes=20,
        total_bytes=30,
        free_bytes=1,
        min_free=10,
    )

    assert not snapshot.ok
    joined = " ".join(snapshot.violations)
    assert "temp usage" in joined
    assert "archive usage" in joined
    assert "total data usage" in joined
    assert "free disk space" in joined


def test_monitor_enforce_raises(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "big.bin").write_bytes(b"x" * 100)

    config = QuotaConfig(
        enabled=True,
        data_dir=data_dir,
        temp_dir=tmp_path / "tmp",
        archive_dir=tmp_path / "archives",
        max_total_bytes=50,
        min_free_bytes=0,
    )
    monitor = QuotaMonitor(config, disk_usage=lambda _path: type("D", (), {"free": 10**12})())

    with pytest.raises(QuotaExceeded) as exc_info:
        monitor.enforce()

    assert "total data usage" in str(exc_info.value)


def test_monitor_enforce_passes_within_limits(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    config = QuotaConfig(
        enabled=True,
        data_dir=data_dir,
        temp_dir=tmp_path / "tmp",
        archive_dir=tmp_path / "archives",
        max_total_bytes=10**6,
        min_free_bytes=0,
    )
    monitor = QuotaMonitor(config, disk_usage=lambda _path: type("D", (), {"free": 10**12})())

    snapshot = monitor.enforce()

    assert snapshot.ok
    assert snapshot.total_bytes == 0


def test_disabled_monitor_never_raises(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "big.bin").write_bytes(b"x" * 100)

    config = QuotaConfig(
        enabled=False,
        data_dir=data_dir,
        temp_dir=tmp_path / "tmp",
        archive_dir=tmp_path / "archives",
        max_total_bytes=1,
        min_free_bytes=0,
    )
    monitor = QuotaMonitor(config, disk_usage=lambda _path: type("D", (), {"free": 0})())

    assert monitor.enforce().total_bytes == 100
