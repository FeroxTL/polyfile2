"""Configuration model and TOML loader for the Polyfile performance harness.

The harness is intentionally a separate project: it depends on locust, httpx,
psutil and plotly, which should not become runtime dependencies of Polyfile
itself. Configuration can come from a TOML file, environment variables and CLI
flags, in that order of precedence (CLI wins).
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, replace
from datetime import timedelta
from pathlib import Path
from typing import Any, Final

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH: Final[Path] = PROJECT_ROOT / "perf.toml"
DEFAULT_OUTPUT_DIR: Final[Path] = PROJECT_ROOT / "runs"
DEFAULT_API_KEY_ENV: Final[str] = "POLYFILE_API_KEY"
CONFIG_ENV: Final[str] = "POLYFILE_PERF_CONFIG"

_SIZE_UNITS: Final[dict[str, int]] = {
    "b": 1,
    "kb": 1024,
    "mb": 1024**2,
    "gb": 1024**3,
    "tb": 1024**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}

_DURATION_UNITS: Final[dict[str, int]] = {
    "s": 1,
    "m": 60,
    "h": 60 * 60,
    "d": 24 * 60 * 60,
}

_SIZE_SUFFIXES: Final[tuple[str, ...]] = tuple(sorted(_SIZE_UNITS, key=len, reverse=True))


class ConfigError(ValueError):
    """Raised when the harness configuration is invalid."""


def parse_size(value: str | int) -> int:
    """Parse ``512MB``/``1GiB``/``1024`` into a byte count."""
    if isinstance(value, int):
        if value < 0:
            raise ConfigError(f"Size must not be negative: {value!r}")
        return value

    text = value.strip().lower()
    for suffix in _SIZE_SUFFIXES:
        if not text.endswith(suffix):
            continue
        number = text[: -len(suffix)].strip()
        try:
            amount = float(number)
        except ValueError as exc:
            raise ConfigError(f"Invalid size: {value!r}") from exc
        if amount < 0:
            raise ConfigError(f"Size must not be negative: {value!r}")
        return int(amount * _SIZE_UNITS[suffix])

    try:
        return int(text)
    except ValueError as exc:
        raise ConfigError(f"Invalid size: {value!r}") from exc


def parse_duration(value: str | int | timedelta) -> timedelta:
    """Parse ``30s``/``5m``/``1h`` into a :class:`datetime.timedelta`."""
    if isinstance(value, timedelta):
        return value
    if isinstance(value, int):
        return timedelta(seconds=value)

    text = value.strip().lower()
    if len(text) < 2 or text[-1] not in _DURATION_UNITS:
        raise ConfigError(f"Invalid duration: {value!r}")
    try:
        amount = float(text[:-1])
    except ValueError as exc:
        raise ConfigError(f"Invalid duration: {value!r}") from exc
    if amount < 0:
        raise ConfigError(f"Duration must not be negative: {value!r}")
    return timedelta(seconds=amount * _DURATION_UNITS[text[-1]])


def format_duration(value: timedelta) -> str:
    """Format a duration for the locust ``--run-time`` flag."""
    seconds = int(value.total_seconds())
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


@dataclass(frozen=True)
class TargetConfig:
    """Where the harness sends requests and how it authenticates."""

    base_url: str = "http://127.0.0.1:8000"
    api_key: str | None = None
    api_key_env: str = DEFAULT_API_KEY_ENV
    timeout: float = 30.0
    verify_tls: bool = True

    def resolve_api_key(self) -> str | None:
        """Return the explicit key or the one stored in the configured env var."""
        return self.api_key or os.environ.get(self.api_key_env) or None

    def normalized_base_url(self) -> str:
        """Return ``base_url`` without a trailing slash."""
        return self.base_url.rstrip("/")


@dataclass(frozen=True)
class QuotaConfig:
    """Disk-usage guard.

    The harness only observes directories; it never deletes files. When a
    configured limit is exceeded the run is aborted so a load test cannot fill
    the machine's disk.
    """

    enabled: bool = True
    data_dir: Path = Path("local")
    temp_dir: Path | None = None
    archive_dir: Path | None = None
    max_temp_bytes: int = 512 * 1024**2
    max_archive_bytes: int = 1024**3
    max_total_bytes: int = 2 * 1024**3
    min_free_bytes: int = 2 * 1024**3
    poll_interval: float = 5.0

    def resolved_data_dir(self) -> Path:
        """Return the Polyfile data directory, honoring ``POLYFILE_DATA_DIR``."""
        raw = os.environ.get("POLYFILE_DATA_DIR")
        path = Path(raw).expanduser() if raw else self.data_dir.expanduser()
        return path if path.is_absolute() else (PROJECT_ROOT.parent / path)

    def resolved_archive_dir(self) -> Path:
        """Return the directory where Polyfile writes ZIP archives."""
        if self.archive_dir is not None:
            return self.archive_dir.expanduser()
        return self.resolved_data_dir() / "archives"

    def resolved_temp_dir(self) -> Path:
        """Return the directory used for temporary upload spooling.

        Polyfile itself uses the process-wide temp directory. By default the
        harness watches ``<data_dir>/tmp`` so it never scans unrelated system
        temp files; point ``temp_dir`` at ``TMPDIR``/``TEMP`` when the server
        is configured that way.
        """
        if self.temp_dir is not None:
            return self.temp_dir.expanduser()
        return self.resolved_data_dir() / "tmp"


@dataclass(frozen=True)
class LoadProfile:
    """A named load-test shape."""

    name: str
    users: int = 5
    spawn_rate: float = 1.0
    duration: timedelta = timedelta(seconds=30)
    wait_min: float = 0.5
    wait_max: float = 2.0
    scenario: str = "mixed"

    def __post_init__(self) -> None:
        if self.users < 1:
            raise ConfigError(f"Profile {self.name!r}: users must be >= 1")
        if self.spawn_rate <= 0:
            raise ConfigError(f"Profile {self.name!r}: spawn_rate must be > 0")
        if self.duration.total_seconds() <= 0:
            raise ConfigError(f"Profile {self.name!r}: duration must be > 0")
        if self.wait_min < 0 or self.wait_max < self.wait_min:
            raise ConfigError(f"Profile {self.name!r}: invalid wait bounds")


BUILTIN_PROFILES: Final[dict[str, LoadProfile]] = {
    "smoke": LoadProfile(
        name="smoke",
        users=1,
        spawn_rate=1.0,
        duration=timedelta(seconds=10),
        wait_min=0.2,
        wait_max=0.5,
        scenario="mixed",
    ),
    "read": LoadProfile(
        name="read",
        users=20,
        spawn_rate=2.0,
        duration=timedelta(minutes=1),
        wait_min=0.2,
        wait_max=1.0,
        scenario="read",
    ),
    "write": LoadProfile(
        name="write",
        users=10,
        spawn_rate=1.0,
        duration=timedelta(minutes=1),
        wait_min=0.5,
        wait_max=2.0,
        scenario="write",
    ),
    "mixed": LoadProfile(
        name="mixed",
        users=20,
        spawn_rate=2.0,
        duration=timedelta(minutes=2),
        wait_min=0.5,
        wait_max=2.0,
        scenario="mixed",
    ),
}


@dataclass(frozen=True)
class HarnessConfig:
    """Top-level configuration for a harness run."""

    target: TargetConfig = field(default_factory=TargetConfig)
    quota: QuotaConfig = field(default_factory=QuotaConfig)
    profiles: dict[str, LoadProfile] = field(
        default_factory=lambda: dict(BUILTIN_PROFILES),
    )
    output_dir: Path = DEFAULT_OUTPUT_DIR

    def profile(self, name: str) -> LoadProfile:
        """Return a profile by name or raise :class:`ConfigError`."""
        try:
            return self.profiles[name]
        except KeyError as exc:
            known = ", ".join(sorted(self.profiles))
            raise ConfigError(f"Unknown profile {name!r}. Known profiles: {known}") from exc


def load_config(path: Path | None = None) -> HarnessConfig:
    """Load the harness configuration from TOML plus environment overrides."""
    config_path = _resolve_config_path(path)
    data: dict[str, Any] = {}
    if config_path is not None:
        try:
            data = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"Cannot read config {config_path}: {exc}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {config_path}: {exc}") from exc

    target = _load_target(data.get("target", {}))
    quota = _load_quota(data.get("quota", {}))
    profiles = _load_profiles(data.get("profiles", {}))
    output_dir = _load_output_dir(data.get("output_dir"))

    return HarnessConfig(
        target=target,
        quota=quota,
        profiles=profiles,
        output_dir=output_dir,
    )


def with_overrides(
    config: HarnessConfig,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    disable_quota: bool = False,
    output_dir: Path | None = None,
) -> HarnessConfig:
    """Return a copy of ``config`` with CLI-level overrides applied."""
    target = replace(
        config.target,
        base_url=base_url or config.target.base_url,
        api_key=api_key or config.target.api_key,
    )
    quota = replace(config.quota, enabled=False) if disable_quota else config.quota
    return replace(
        config,
        target=target,
        quota=quota,
        output_dir=output_dir or config.output_dir,
    )


def _resolve_config_path(path: Path | None) -> Path | None:
    if path is not None:
        resolved = Path(path).expanduser()
        if not resolved.exists():
            raise ConfigError(f"Config file not found: {resolved}")
        return resolved

    env_path = os.environ.get(CONFIG_ENV)
    if env_path:
        resolved = Path(env_path).expanduser()
        if not resolved.exists():
            raise ConfigError(f"Config file from {CONFIG_ENV} not found: {resolved}")
        return resolved

    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    return None


def _load_target(raw: dict[str, Any]) -> TargetConfig:
    base_url = os.environ.get("POLYFILE_PERF_BASE_URL") or str(
        raw.get("base_url", TargetConfig.base_url),
    )
    api_key = os.environ.get("POLYFILE_API_KEY") or raw.get("api_key")
    api_key_env = str(raw.get("api_key_env", DEFAULT_API_KEY_ENV))
    timeout = float(raw.get("timeout", 30.0))
    verify_tls = bool(raw.get("verify_tls", True))
    return TargetConfig(
        base_url=base_url,
        api_key=api_key,
        api_key_env=api_key_env,
        timeout=timeout,
        verify_tls=verify_tls,
    )


def _load_quota(raw: dict[str, Any]) -> QuotaConfig:
    defaults = QuotaConfig()
    data_dir = Path(raw.get("data_dir", defaults.data_dir))
    temp_dir = raw.get("temp_dir")
    archive_dir = raw.get("archive_dir")
    return QuotaConfig(
        enabled=bool(raw.get("enabled", defaults.enabled)),
        data_dir=data_dir,
        temp_dir=Path(temp_dir) if temp_dir else None,
        archive_dir=Path(archive_dir) if archive_dir else None,
        max_temp_bytes=parse_size(raw.get("max_temp_bytes", defaults.max_temp_bytes)),
        max_archive_bytes=parse_size(raw.get("max_archive_bytes", defaults.max_archive_bytes)),
        max_total_bytes=parse_size(raw.get("max_total_bytes", defaults.max_total_bytes)),
        min_free_bytes=parse_size(raw.get("min_free_bytes", defaults.min_free_bytes)),
        poll_interval=float(raw.get("poll_interval", defaults.poll_interval)),
    )


def _load_profiles(raw: dict[str, Any]) -> dict[str, LoadProfile]:
    profiles = dict(BUILTIN_PROFILES)
    for name, values in raw.items():
        if not isinstance(values, dict):
            raise ConfigError(f"Profile {name!r} must be a table")
        base = profiles.get(name, LoadProfile(name=name))
        profiles[name] = replace(
            base,
            name=name,
            users=int(values.get("users", base.users)),
            spawn_rate=float(values.get("spawn_rate", base.spawn_rate)),
            duration=parse_duration(values.get("duration", base.duration)),
            wait_min=float(values.get("wait_min", base.wait_min)),
            wait_max=float(values.get("wait_max", base.wait_max)),
            scenario=str(values.get("scenario", base.scenario)),
        )
    return profiles


def _load_output_dir(raw: Any) -> Path:
    env_value = os.environ.get("POLYFILE_PERF_OUTPUT_DIR")
    if env_value:
        return Path(env_value).expanduser()
    if raw:
        path = Path(str(raw)).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path
    return DEFAULT_OUTPUT_DIR
