from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from polyfile_perf.config import (
    PROJECT_ROOT,
    ConfigError,
    LoadProfile,
    format_duration,
    load_config,
    parse_duration,
    parse_size,
    with_overrides,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "POLYFILE_API_KEY",
        "POLYFILE_PERF_BASE_URL",
        "POLYFILE_PERF_CONFIG",
        "POLYFILE_PERF_OUTPUT_DIR",
        "POLYFILE_DATA_DIR",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1024, 1024),
        ("1024", 1024),
        ("1KB", 1024),
        ("512MB", 512 * 1024**2),
        ("1GiB", 1024**3),
        ("2gb", 2 * 1024**3),
    ],
)
def test_parse_size(value: str | int, expected: int) -> None:
    assert parse_size(value) == expected


def test_parse_size_rejects_garbage() -> None:
    with pytest.raises(ConfigError):
        parse_size("large")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30s", timedelta(seconds=30)),
        ("5m", timedelta(minutes=5)),
        ("1h", timedelta(hours=1)),
        (15, timedelta(seconds=15)),
        (timedelta(seconds=7), timedelta(seconds=7)),
    ],
)
def test_parse_duration(value: str | int | timedelta, expected: timedelta) -> None:
    assert parse_duration(value) == expected


def test_parse_duration_rejects_garbage() -> None:
    with pytest.raises(ConfigError):
        parse_duration("soon")


def test_format_duration() -> None:
    assert format_duration(timedelta(seconds=30)) == "30s"
    assert format_duration(timedelta(minutes=2)) == "2m"
    assert format_duration(timedelta(hours=1)) == "1h"


def test_load_config_reads_profiles_and_quota(tmp_path: Path) -> None:
    config_path = tmp_path / "perf.toml"
    config_path.write_text(
        """
output_dir = "custom-runs"

[target]
base_url = "http://example.test:9000"
timeout = 5.0

[quota]
data_dir = "data"
max_total_bytes = "3GB"
poll_interval = 1.5

[profiles.smoke]
users = 2
duration = "20s"
scenario = "read"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.target.base_url == "http://example.test:9000"
    assert config.target.timeout == 5.0
    assert config.quota.max_total_bytes == 3 * 1024**3
    assert config.quota.poll_interval == 1.5
    assert config.profile("smoke").users == 2
    assert config.profile("smoke").duration == timedelta(seconds=20)
    assert config.profile("smoke").scenario == "read"
    assert config.output_dir == PROJECT_ROOT / "custom-runs"


def test_load_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.toml")


def test_unknown_profile_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "perf.toml"
    config_path.write_text("[target]\nbase_url = \"http://x\"\n", encoding="utf-8")
    config = load_config(config_path)

    with pytest.raises(ConfigError):
        config.profile("does-not-exist")


def test_environment_overrides_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_path = tmp_path / "perf.toml"
    config_path.write_text("[target]\nbase_url = \"http://from-file\"\n", encoding="utf-8")
    monkeypatch.setenv("POLYFILE_PERF_BASE_URL", "http://from-env")
    monkeypatch.setenv("POLYFILE_API_KEY", "pf_test_key")

    config = load_config(config_path)

    assert config.target.base_url == "http://from-env"
    assert config.target.resolve_api_key() == "pf_test_key"


def test_with_overrides_disables_quota(tmp_path: Path) -> None:
    config_path = tmp_path / "perf.toml"
    config_path.write_text("", encoding="utf-8")
    config = load_config(config_path)

    overridden = with_overrides(
        config,
        base_url="http://override",
        disable_quota=True,
        output_dir=tmp_path / "out",
    )

    assert overridden.target.normalized_base_url() == "http://override"
    assert overridden.quota.enabled is False
    assert overridden.output_dir == tmp_path / "out"


def test_profile_validation() -> None:
    with pytest.raises(ConfigError):
        LoadProfile(name="bad", users=0)
    with pytest.raises(ConfigError):
        LoadProfile(name="bad", spawn_rate=0)
    with pytest.raises(ConfigError):
        LoadProfile(name="bad", duration=timedelta(0))
