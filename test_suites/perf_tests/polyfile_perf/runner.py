"""Run orchestration: smoke runs, locust runs and artifact writing."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from polyfile_perf.client import PolyfileApiError, PolyfileClient
from polyfile_perf.config import (
    PROJECT_ROOT,
    HarnessConfig,
    LoadProfile,
    format_duration,
)
from polyfile_perf.metrics import RequestRecorder, ResourceSampler
from polyfile_perf.quota import QuotaExceeded, QuotaMonitor, UsageSnapshot
from polyfile_perf.report import ReportContext, write_run_artifacts
from polyfile_perf.smoke import SmokeResult, run_smoke_flow

LOCUSTFILE = PROJECT_ROOT / "locustfile.py"
RUN_ERRORS = (
    PolyfileApiError,
    httpx.HTTPError,
    TimeoutError,
    OSError,
    KeyError,
    ValueError,
    AssertionError,
)


@dataclass
class RunOutcome:
    """Result of a smoke or locust run."""

    run_dir: Path
    report_path: Path
    summary: dict[str, Any]
    ok: bool
    smoke: SmokeResult | None = None
    error: str | None = None


def create_run_dir(output_dir: Path, prefix: str) -> Path:
    """Create a unique timestamped directory for a run."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / f"{prefix}-{stamp}"
    suffix = 1
    candidate = run_dir
    while candidate.exists():
        suffix += 1
        candidate = output_dir / f"{prefix}-{stamp}-{suffix}"
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def run_smoke(
    config: HarnessConfig,
    *,
    payload_size: int = 1024,
    out_dir: Path | None = None,
) -> RunOutcome:
    """Run the API smoke flow and write a report."""
    started = datetime.now(UTC)
    run_dir = create_run_dir(out_dir or config.output_dir, "smoke")
    recorder = RequestRecorder()
    sampler = ResourceSampler()
    quota = QuotaMonitor(config.quota)
    notes: list[str] = []
    quota_snapshot: UsageSnapshot | None = None
    violations: list[str] = []
    smoke_result: SmokeResult | None = None
    error: str | None = None

    try:
        quota_snapshot = quota.enforce()
    except QuotaExceeded as exc:
        violations = exc.violations
        error = str(exc)
    else:
        sampler.start()
        try:
            with PolyfileClient(config.target, on_request=recorder.record) as client:
                smoke_result = run_smoke_flow(client, payload_size=payload_size)
        except RUN_ERRORS as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            sampler.stop()

        try:
            quota_snapshot = quota.enforce()
        except QuotaExceeded as exc:
            violations = exc.violations
            error = error or str(exc)

    if smoke_result is not None:
        notes.extend(
            f"{step.name}: {'ok' if step.ok else 'FAILED'} ({step.duration_ms:.0f} ms)"
            + (f" - {step.detail}" if step.detail else "")
            for step in smoke_result.steps
        )
        if not smoke_result.ok:
            error = error or "Smoke flow reported failed steps"

    finished = datetime.now(UTC)
    summary = recorder.summary((finished - started).total_seconds())
    if smoke_result is not None:
        summary["smoke_ok"] = smoke_result.ok
        summary["smoke_failures"] = [step.name for step in smoke_result.failures]

    context = ReportContext(
        title=f"Polyfile smoke run ({config.target.normalized_base_url()})",
        started_at=started,
        finished_at=finished,
        profile="smoke",
        target_url=config.target.normalized_base_url(),
        summary=summary,
        request_samples=recorder.samples,
        resource_samples=sampler.samples,
        quota_snapshot=quota_snapshot,
        quota_violations=violations,
        notes=notes,
    )
    report_path = write_run_artifacts(run_dir, context)
    ok = error is None and (smoke_result is None or smoke_result.ok)
    return RunOutcome(
        run_dir=run_dir,
        report_path=report_path,
        summary=summary,
        ok=ok,
        smoke=smoke_result,
        error=error,
    )


def run_locust(
    config: HarnessConfig,
    profile: LoadProfile,
    *,
    out_dir: Path | None = None,
    extra_args: Iterable[str] = (),
    payload_size: int = 1024,
) -> RunOutcome:
    """Run a locust scenario as a subprocess and write a report."""
    started = datetime.now(UTC)
    run_dir = create_run_dir(out_dir or config.output_dir, f"load-{profile.name}")
    csv_prefix = run_dir / "locust"
    quota = QuotaMonitor(config.quota)
    sampler = ResourceSampler()
    notes: list[str] = []
    violations: list[str] = []
    quota_snapshot: UsageSnapshot | None = None
    error: str | None = None
    return_code = 1

    try:
        quota_snapshot = quota.enforce()
    except QuotaExceeded as exc:
        violations = exc.violations
        error = str(exc)
    else:
        command = _locust_command(config, profile, csv_prefix, extra_args)
        env = _locust_env(config, profile, payload_size)
        notes.append("command: " + " ".join(command))

        sampler.start()
        try:
            process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=env)
        except OSError as exc:
            sampler.stop()
            error = f"{type(exc).__name__}: {exc}"
        else:
            def abort_run(exc: QuotaExceeded) -> None:
                nonlocal violations, error
                violations = exc.violations
                error = str(exc)
                process.terminate()

            quota.start(abort_run)
            try:
                return_code = process.wait()
            finally:
                quota.stop()
                sampler.stop()

            if return_code != 0 and error is None:
                error = f"locust exited with code {return_code}"

            try:
                quota_snapshot = quota.enforce()
            except QuotaExceeded as exc:
                violations = exc.violations
                error = error or str(exc)

    finished = datetime.now(UTC)
    summary, history = read_locust_csv(csv_prefix)
    if not summary:
        notes.append("locust CSV statistics were not found; the run may have failed early.")

    context = ReportContext(
        title=f"Polyfile load run: {profile.name}",
        started_at=started,
        finished_at=finished,
        profile=profile.name,
        target_url=config.target.normalized_base_url(),
        summary=summary,
        resource_samples=sampler.samples,
        locust_history=history,
        quota_snapshot=quota_snapshot,
        quota_violations=violations,
        notes=notes,
    )
    report_path = write_run_artifacts(run_dir, context)
    return RunOutcome(
        run_dir=run_dir,
        report_path=report_path,
        summary=summary,
        ok=error is None and return_code == 0,
        error=error,
    )


def read_locust_csv(csv_prefix: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Parse locust's ``*_stats.csv`` and ``*_stats_history.csv`` files."""
    stats_path = csv_prefix.parent / f"{csv_prefix.name}_stats.csv"
    history_path = csv_prefix.parent / f"{csv_prefix.name}_stats_history.csv"

    summary = _aggregated_stats(stats_path)
    history = _aggregated_history(history_path)
    return summary, history


def _aggregated_stats(path: Path) -> dict[str, Any]:
    rows = _read_csv(path)
    if not rows:
        return {}

    row = next((item for item in rows if item.get("Name") == "Aggregated"), None)
    if row is None:
        row = rows[-1]

    requests = _as_int(row.get("Request Count"))
    failures = _as_int(row.get("Failure Count"))
    return {
        "requests": requests,
        "errors": failures,
        "error_rate": (failures / requests) if requests else 0.0,
        "requests_per_second": _as_float(row.get("Requests/s")),
        "latency_ms": {
            "mean": _as_float(row.get("Average Response Time")),
            "p50": _as_float(row.get("50%")),
            "p90": _as_float(row.get("90%")),
            "p95": _as_float(row.get("95%")),
            "p99": _as_float(row.get("99%")),
            "max": _as_float(row.get("Max Response Time")),
        },
    }


def _aggregated_history(path: Path) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for row in _read_csv(path):
        if row.get("Name") != "Aggregated":
            continue
        history.append(
            {
                "timestamp": _as_timestamp(row.get("Timestamp")),
                "requests_per_second": _as_float(row.get("Requests/s")),
                "failures_per_second": _as_float(row.get("Failures/s")),
                "p95": _as_float(row.get("95%")),
                "user_count": _as_int(row.get("User Count")),
            }
        )
    return history


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _as_timestamp(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _locust_command(
    config: HarnessConfig,
    profile: LoadProfile,
    csv_prefix: Path,
    extra_args: Iterable[str],
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(LOCUSTFILE),
        "--headless",
        "--host",
        config.target.normalized_base_url(),
        "--users",
        str(profile.users),
        "--spawn-rate",
        str(profile.spawn_rate),
        "--run-time",
        format_duration(profile.duration),
        "--csv",
        str(csv_prefix),
        "--html",
        str(csv_prefix.parent / "locust.html"),
        "--only-summary",
        "--exit-code-on-error",
        "1",
    ]
    if profile.scenario != "mixed":
        command.extend(["--tags", profile.scenario])
    command.extend(extra_args)
    return command


def _locust_env(
    config: HarnessConfig,
    profile: LoadProfile,
    payload_size: int,
) -> dict[str, str]:
    env = dict(os.environ)
    api_key = config.target.resolve_api_key()
    if api_key:
        env["POLYFILE_API_KEY"] = api_key
    env["PERF_SCENARIO"] = profile.scenario
    env["PERF_WAIT_MIN"] = str(profile.wait_min)
    env["PERF_WAIT_MAX"] = str(profile.wait_max)
    env["PERF_PAYLOAD_SIZE"] = str(payload_size)
    return env


def write_outcome_summary(outcome: RunOutcome) -> str:
    """Render a short human-readable summary for the CLI."""
    payload = {
        "ok": outcome.ok,
        "run_dir": str(outcome.run_dir),
        "report": str(outcome.report_path),
        "summary": outcome.summary,
        "error": outcome.error,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
