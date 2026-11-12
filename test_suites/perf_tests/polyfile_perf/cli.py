"""Command line interface for the Polyfile performance harness."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from polyfile_perf.client import PolyfileClient
from polyfile_perf.config import (
    ConfigError,
    HarnessConfig,
    format_duration,
    load_config,
    parse_duration,
    with_overrides,
)
from polyfile_perf.quota import QuotaExceeded, QuotaMonitor
from polyfile_perf.report import load_run_artifacts, write_run_artifacts
from polyfile_perf.runner import RunOutcome, run_locust, run_smoke, write_outcome_summary


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="polyfile-perf",
        description="Load and performance testing harness for Polyfile.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, help="Path to perf.toml")
    common.add_argument("--base-url", help="Override the Polyfile base URL")
    common.add_argument("--api-key", help="API key (defaults to POLYFILE_API_KEY)")
    common.add_argument(
        "--no-quota",
        action="store_true",
        help="Disable the disk-usage guard (not recommended)",
    )
    common.add_argument("--out", type=Path, help="Output directory for run artifacts")

    smoke = subparsers.add_parser(
        "smoke",
        parents=[common],
        help="Run the end-to-end API smoke flow",
    )
    smoke.add_argument("--payload-size", type=int, default=1024, help="Upload size in bytes")
    smoke.add_argument("--json", action="store_true", help="Print a JSON summary")
    smoke.set_defaults(handler=_handle_smoke)

    run = subparsers.add_parser("run", parents=[common], help="Run a locust load scenario")
    run.add_argument("--profile", default="smoke", help="Profile name (see 'profiles')")
    run.add_argument("--users", type=int, help="Override concurrent users")
    run.add_argument("--spawn-rate", type=float, help="Override users spawned per second")
    run.add_argument("--duration", help="Override duration such as 30s, 5m or 1h")
    run.add_argument("--payload-size", type=int, default=1024, help="Upload size in bytes")
    run.add_argument(
        "--locust-arg",
        action="append",
        default=[],
        help="Extra argument passed to locust (repeatable)",
    )
    run.add_argument("--json", action="store_true", help="Print a JSON summary")
    run.set_defaults(handler=_handle_run)

    check = subparsers.add_parser(
        "check",
        parents=[common],
        help="Check quota limits and API authentication",
    )
    check.set_defaults(handler=_handle_check)

    profiles = subparsers.add_parser("profiles", parents=[common], help="List profiles")
    profiles.add_argument("--json", action="store_true", help="Print JSON")
    profiles.set_defaults(handler=_handle_profiles)

    report = subparsers.add_parser("report", help="Rebuild a report from a run directory")
    report.add_argument("run_dir", type=Path, help="Run directory produced by smoke/run")
    report.set_defaults(handler=_handle_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args) or 0)
    except (ConfigError, QuotaExceeded) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _config_from_args(args: argparse.Namespace) -> HarnessConfig:
    config = load_config(args.config)
    return with_overrides(
        config,
        base_url=args.base_url,
        api_key=args.api_key,
        disable_quota=args.no_quota,
        output_dir=args.out,
    )


def _handle_smoke(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    outcome = run_smoke(config, payload_size=args.payload_size)
    _print_outcome(outcome, as_json=args.json)
    return 0 if outcome.ok else 1


def _handle_run(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    profile = config.profile(args.profile)
    if args.users is not None:
        profile = replace(profile, users=args.users)
    if args.spawn_rate is not None:
        profile = replace(profile, spawn_rate=args.spawn_rate)
    if args.duration:
        profile = replace(profile, duration=parse_duration(args.duration))

    outcome = run_locust(
        config,
        profile,
        extra_args=args.locust_arg,
        payload_size=args.payload_size,
    )
    _print_outcome(outcome, as_json=args.json)
    return 0 if outcome.ok else 1


def _handle_check(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    monitor = QuotaMonitor(config.quota)
    snapshot = monitor.enforce()
    print(
        f"quota: ok (temp {snapshot.temp_bytes} B, archive {snapshot.archive_bytes} B, "
        f"free {snapshot.free_bytes} B)"
    )

    with PolyfileClient(config.target) as client:
        payload = client.dashboard_context()
    print(f"auth: ok ({config.target.normalized_base_url()}, {len(payload)} keys)")
    return 0


def _handle_profiles(args: argparse.Namespace) -> int:
    config = _config_from_args(args)
    if args.json:
        print(
            json.dumps(
                {
                    name: {
                        "users": profile.users,
                        "spawn_rate": profile.spawn_rate,
                        "duration": format_duration(profile.duration),
                        "scenario": profile.scenario,
                        "wait_min": profile.wait_min,
                        "wait_max": profile.wait_max,
                    }
                    for name, profile in sorted(config.profiles.items())
                },
                indent=2,
            )
        )
        return 0

    print(f"{'name':<10}{'users':>7}{'spawn/s':>9}{'duration':>10}  scenario")
    for name, profile in sorted(config.profiles.items()):
        print(
            f"{name:<10}{profile.users:>7}{profile.spawn_rate:>9.1f}"
            f"{format_duration(profile.duration):>10}  {profile.scenario}"
        )
    return 0


def _handle_report(args: argparse.Namespace) -> int:
    context = load_run_artifacts(args.run_dir)
    path = write_run_artifacts(args.run_dir, context)
    print(f"report: {path}")
    return 0


def _print_outcome(outcome: RunOutcome, *, as_json: bool) -> None:
    if as_json:
        print(write_outcome_summary(outcome))
        return

    status = "OK" if outcome.ok else "FAILED"
    print(f"{status}: {outcome.run_dir.name} ({outcome.report_path})")
    if outcome.smoke is not None:
        for step in outcome.smoke.steps:
            marker = "ok" if step.ok else "FAILED"
            detail = f" - {step.detail}" if step.detail else ""
            print(f"  {step.name:<20}{marker:>7} {step.duration_ms:>8.0f} ms{detail}")
    if outcome.error:
        print(f"  error: {outcome.error}")
    print(f"  report: {outcome.report_path}")


if __name__ == "__main__":
    raise SystemExit(main())
