from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from polyfile_perf.metrics import RequestSample, ResourceSample
from polyfile_perf.quota import UsageSnapshot
from polyfile_perf.report import (
    ReportContext,
    build_html,
    load_run_artifacts,
    write_run_artifacts,
)


def make_context() -> ReportContext:
    started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    return ReportContext(
        title="Test run",
        started_at=started,
        finished_at=started + timedelta(seconds=10),
        profile="smoke",
        target_url="http://polyfile.test",
        summary={
            "requests": 2,
            "errors": 1,
            "error_rate": 0.5,
            "requests_per_second": 0.2,
            "latency_ms": {"mean": 10.0, "p50": 10.0, "p95": 20.0, "p99": 20.0, "max": 20.0},
            "status_counts": {"200": 1, "500": 1},
        },
        request_samples=[
            RequestSample(0.0, "GET", "/api/v1/fs-node/", 200, 10.0),
            RequestSample(1.0, "GET", "/api/v1/fs-node/", 500, 20.0),
        ],
        resource_samples=[
            ResourceSample(0.0, 10.0, 20.0, 1024, 0, 0),
        ],
        quota_snapshot=UsageSnapshot(
            timestamp=0.0,
            temp_bytes=1,
            archive_bytes=2,
            total_bytes=3,
            free_bytes=4,
            temp_limit=10,
            archive_limit=10,
            total_limit=10,
            min_free=0,
        ),
        notes=["smoke: ok"],
    )


def test_build_html_contains_summary_and_charts() -> None:
    html = build_html(make_context())

    assert "<title>Test run</title>" in html
    assert "Requests / second" in html
    assert "All quota limits satisfied." in html
    assert "smoke: ok" in html
    assert "plotly" in html.lower()


def test_write_and_load_artifacts_roundtrip(tmp_path: Path) -> None:
    context = make_context()

    report_path = write_run_artifacts(tmp_path, context)

    assert report_path.exists()
    loaded = load_run_artifacts(tmp_path)
    assert loaded.title == context.title
    assert loaded.profile == context.profile
    assert loaded.summary["requests"] == 2
    assert len(loaded.request_samples) == 2
    assert len(loaded.resource_samples) == 1
    assert loaded.quota_snapshot is not None
    assert loaded.quota_snapshot.total_bytes == 3
    assert loaded.notes == ["smoke: ok"]
    assert loaded.duration_seconds == 10.0


def test_quota_violations_are_rendered() -> None:
    context = make_context()
    context.quota_violations = ["temp usage 1.0 KiB exceeds limit 1.0 B"]

    html = build_html(context)

    assert "Quota exceeded" in html
