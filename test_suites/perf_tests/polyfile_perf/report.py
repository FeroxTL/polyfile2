"""Static HTML report generation.

Reports are self-contained: plotly.js is embedded once, so a report can be
copied off the machine and opened without network access.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from polyfile_perf.metrics import RequestSample, ResourceSample
from polyfile_perf.quota import UsageSnapshot, format_bytes

SUMMARY_FILE = "summary.json"
REQUESTS_FILE = "requests.jsonl"
RESOURCES_FILE = "resources.jsonl"
REPORT_FILE = "report.html"


@dataclass
class ReportContext:
    """Everything needed to render a run report."""

    title: str
    started_at: datetime
    finished_at: datetime
    profile: str
    target_url: str
    summary: dict[str, Any]
    request_samples: list[RequestSample] = field(default_factory=list)
    resource_samples: list[ResourceSample] = field(default_factory=list)
    locust_history: list[dict[str, Any]] = field(default_factory=list)
    quota_snapshot: UsageSnapshot | None = None
    quota_violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        """Return the wall-clock duration of the run."""
        return max(0.0, (self.finished_at - self.started_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        """Serialize the context for ``summary.json``."""
        return {
            "title": self.title,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "profile": self.profile,
            "target_url": self.target_url,
            "summary": self.summary,
            "quota_snapshot": (
                {
                    "timestamp": self.quota_snapshot.timestamp,
                    "temp_bytes": self.quota_snapshot.temp_bytes,
                    "archive_bytes": self.quota_snapshot.archive_bytes,
                    "total_bytes": self.quota_snapshot.total_bytes,
                    "free_bytes": self.quota_snapshot.free_bytes,
                    "temp_limit": self.quota_snapshot.temp_limit,
                    "archive_limit": self.quota_snapshot.archive_limit,
                    "total_limit": self.quota_snapshot.total_limit,
                    "min_free": self.quota_snapshot.min_free,
                }
                if self.quota_snapshot
                else None
            ),
            "quota_violations": self.quota_violations,
            "notes": self.notes,
            "locust_history": self.locust_history,
        }


def write_run_artifacts(run_dir: Path, context: ReportContext) -> Path:
    """Write summary JSON, JSONL samples and the HTML report; return the report path."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / SUMMARY_FILE).write_text(
        json.dumps(context.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_jsonl(run_dir / REQUESTS_FILE, context.request_samples)
    _write_jsonl(run_dir / RESOURCES_FILE, context.resource_samples)
    report_path = run_dir / REPORT_FILE
    report_path.write_text(build_html(context), encoding="utf-8")
    return report_path


def load_run_artifacts(run_dir: Path) -> ReportContext:
    """Rebuild a report context from previously written artifacts."""
    summary_path = run_dir / SUMMARY_FILE
    if not summary_path.exists():
        raise FileNotFoundError(f"Missing {summary_path}")

    data = json.loads(summary_path.read_text(encoding="utf-8"))
    quota_data = data.get("quota_snapshot")
    return ReportContext(
        title=str(data.get("title", "Polyfile perf run")),
        started_at=datetime.fromisoformat(data["started_at"]),
        finished_at=datetime.fromisoformat(data["finished_at"]),
        profile=str(data.get("profile", "")),
        target_url=str(data.get("target_url", "")),
        summary=dict(data.get("summary", {})),
        request_samples=_read_samples(run_dir / REQUESTS_FILE, RequestSample),
        resource_samples=_read_samples(run_dir / RESOURCES_FILE, ResourceSample),
        locust_history=list(data.get("locust_history", [])),
        quota_snapshot=UsageSnapshot(**quota_data) if quota_data else None,
        quota_violations=list(data.get("quota_violations", [])),
        notes=list(data.get("notes", [])),
    )


def build_html(context: ReportContext) -> str:
    """Render the report as a self-contained HTML document."""
    figures: list[str] = []
    include_js = True

    if context.locust_history:
        figures.append(_figure_html(_locust_throughput_figure(context.locust_history), include_js))
        include_js = False
    elif context.request_samples:
        figures.append(_figure_html(_latency_figure(context.request_samples), include_js))
        include_js = False
        figures.append(_figure_html(_throughput_figure(context.request_samples), False))

    if context.request_samples:
        figures.append(_figure_html(_status_figure(context.request_samples), False))

    if context.resource_samples:
        figures.append(_figure_html(_resource_figure(context.resource_samples), False))

    summary_rows = _summary_rows(context)
    quota_block = _quota_block(context)
    notes_block = _notes_block(context)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(context.title)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; padding: 24px; background: #f6f7f9; color: #1f2328; }}
  h1 {{ margin: 0 0 4px; font-size: 24px; }}
  h2 {{ margin: 28px 0 12px; font-size: 18px; }}
  .meta {{ color: #57606a; font-size: 14px; }}
  .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
           padding: 16px 20px; margin-top: 16px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 6px 10px; border-bottom: 1px solid #eaeef2; }}
  th {{ color: #57606a; font-weight: 600; }}
  .ok {{ color: #1a7f37; font-weight: 600; }}
  .bad {{ color: #cf222e; font-weight: 600; }}
  .chart {{ margin-top: 12px; }}
  ul {{ margin: 8px 0 0; padding-left: 20px; }}
</style>
</head>
<body>
<h1>{html.escape(context.title)}</h1>
<p class="meta">
  Profile <strong>{html.escape(context.profile)}</strong> &middot;
  target <code>{html.escape(context.target_url)}</code> &middot;
  {html.escape(context.started_at.isoformat(timespec="seconds"))} &rarr;
  {html.escape(context.finished_at.isoformat(timespec="seconds"))}
  ({context.duration_seconds:.1f}s)
</p>

<div class="card">
  <h2>Summary</h2>
  <table>
    <tbody>
      {summary_rows}
    </tbody>
  </table>
</div>

{quota_block}
{notes_block}

{''.join(f'<div class="card chart">{figure}</div>' for figure in figures)}
</body>
</html>
"""


def _summary_rows(context: ReportContext) -> str:
    summary = context.summary
    latency = summary.get("latency_ms", {}) if isinstance(summary, dict) else {}
    rows: list[tuple[str, Any]] = [
        ("Requests", summary.get("requests", 0)),
        ("Errors", summary.get("errors", 0)),
        ("Error rate", f"{float(summary.get('error_rate', 0.0)) * 100:.2f}%"),
        ("Requests / second", f"{float(summary.get('requests_per_second', 0.0)):.2f}"),
        ("Latency mean", f"{float(latency.get('mean', 0.0)):.1f} ms"),
        ("Latency p95", f"{float(latency.get('p95', 0.0)):.1f} ms"),
        ("Latency p99", f"{float(latency.get('p99', 0.0)):.1f} ms"),
    ]
    status_counts = summary.get("status_counts") or {}
    if status_counts:
        rendered = ", ".join(f"{key}: {value}" for key, value in sorted(status_counts.items()))
        rows.append(("Status codes", rendered))

    return "\n".join(
        f"<tr><th>{html.escape(str(label))}</th><td>{html.escape(str(value))}</td></tr>"
        for label, value in rows
    )


def _quota_block(context: ReportContext) -> str:
    snapshot = context.quota_snapshot
    if snapshot is None and not context.quota_violations:
        return ""

    rows = ""
    if snapshot is not None:
        rows = (
            f"<tr><th>Temp bytes</th><td>{format_bytes(snapshot.temp_bytes)}</td></tr>"
            f"<tr><th>Archive bytes</th><td>{format_bytes(snapshot.archive_bytes)}</td></tr>"
            f"<tr><th>Data dir bytes</th><td>{format_bytes(snapshot.total_bytes)}</td></tr>"
            f"<tr><th>Free disk</th><td>{format_bytes(snapshot.free_bytes)}</td></tr>"
        )

    if context.quota_violations:
        status = (
            '<p class="bad">Quota exceeded: '
            + html.escape("; ".join(context.quota_violations))
            + "</p>"
        )
    else:
        status = '<p class="ok">All quota limits satisfied.</p>'

    return f'<div class="card"><h2>Disk usage</h2><table><tbody>{rows}</tbody></table>{status}</div>'


def _notes_block(context: ReportContext) -> str:
    if not context.notes:
        return ""
    items = "".join(f"<li>{html.escape(note)}</li>" for note in context.notes)
    return f'<div class="card"><h2>Notes</h2><ul>{items}</ul></div>'


def _latency_figure(samples: list[RequestSample]) -> go.Figure:
    start = min(sample.timestamp for sample in samples)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[sample.timestamp - start for sample in samples],
            y=[sample.elapsed_ms for sample in samples],
            mode="markers",
            marker={
                "size": 4,
                "color": ["#1a7f37" if sample.ok else "#cf222e" for sample in samples],
            },
            text=[f"{sample.method} {sample.path} ({sample.status_code})" for sample in samples],
            hovertemplate="%{text}<br>%{y:.1f} ms<extra></extra>",
        )
    )
    figure.update_layout(
        title="Request latency",
        xaxis_title="Seconds since start",
        yaxis_title="Latency (ms)",
        margin={"l": 60, "r": 20, "t": 50, "b": 50},
        height=380,
    )
    return figure


def _throughput_figure(samples: list[RequestSample]) -> go.Figure:
    start = min(sample.timestamp for sample in samples)
    buckets: dict[int, int] = {}
    for sample in samples:
        second = int(sample.timestamp - start)
        buckets[second] = buckets.get(second, 0) + 1

    figure = go.Figure(
        go.Bar(
            x=sorted(buckets),
            y=[buckets[key] for key in sorted(buckets)],
            marker_color="#0969da",
        )
    )
    figure.update_layout(
        title="Throughput",
        xaxis_title="Seconds since start",
        yaxis_title="Requests",
        margin={"l": 60, "r": 20, "t": 50, "b": 50},
        height=320,
    )
    return figure


def _status_figure(samples: list[RequestSample]) -> go.Figure:
    counts: dict[str, int] = {}
    for sample in samples:
        key = str(sample.status_code)
        counts[key] = counts.get(key, 0) + 1
    labels = sorted(counts)
    figure = go.Figure(
        go.Bar(
            x=labels,
            y=[counts[key] for key in labels],
            marker_color=["#cf222e" if not key.startswith(("2", "3")) else "#1a7f37" for key in labels],
        )
    )
    figure.update_layout(
        title="Responses by status code",
        xaxis_title="Status code",
        yaxis_title="Requests",
        margin={"l": 60, "r": 20, "t": 50, "b": 50},
        height=300,
    )
    return figure


def _locust_throughput_figure(history: list[dict[str, Any]]) -> go.Figure:
    timestamps = [float(point["timestamp"]) for point in history]
    start = min(timestamps) if timestamps else 0.0
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[value - start for value in timestamps],
            y=[float(point.get("requests_per_second", 0.0)) for point in history],
            mode="lines",
            name="Requests/s",
            line={"color": "#0969da"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[value - start for value in timestamps],
            y=[float(point.get("p95", 0.0)) for point in history],
            mode="lines",
            name="p95 (ms)",
            yaxis="y2",
            line={"color": "#cf222e"},
        )
    )
    figure.update_layout(
        title="Locust throughput and p95 latency",
        xaxis_title="Seconds since start",
        yaxis={"title": "Requests/s"},
        yaxis2={"title": "p95 (ms)", "overlaying": "y", "side": "right"},
        margin={"l": 60, "r": 60, "t": 50, "b": 50},
        height=380,
        legend={"orientation": "h"},
    )
    return figure


def _resource_figure(samples: list[ResourceSample]) -> go.Figure:
    start = min(sample.timestamp for sample in samples)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=[sample.timestamp - start for sample in samples],
            y=[sample.cpu_percent for sample in samples],
            mode="lines",
            name="CPU %",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[sample.timestamp - start for sample in samples],
            y=[sample.memory_percent for sample in samples],
            mode="lines",
            name="Memory %",
        )
    )
    figure.update_layout(
        title="Machine resource usage",
        xaxis_title="Seconds since start",
        yaxis_title="Percent",
        margin={"l": 60, "r": 20, "t": 50, "b": 50},
        height=320,
        legend={"orientation": "h"},
    )
    return figure


def _figure_html(figure: go.Figure, include_plotlyjs: bool) -> str:
    return figure.to_html(
        full_html=False,
        include_plotlyjs="inline" if include_plotlyjs else False,
        config={"displayModeBar": False, "responsive": True},
    )


def _write_jsonl(path: Path, samples: list[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(_sample_dict(sample), ensure_ascii=False))
            handle.write("\n")


def _sample_dict(sample: Any) -> dict[str, Any]:
    if isinstance(sample, RequestSample):
        return {
            "timestamp": sample.timestamp,
            "method": sample.method,
            "path": sample.path,
            "status_code": sample.status_code,
            "elapsed_ms": sample.elapsed_ms,
        }
    return {
        "timestamp": sample.timestamp,
        "cpu_percent": sample.cpu_percent,
        "memory_percent": sample.memory_percent,
        "memory_used_bytes": sample.memory_used_bytes,
        "disk_read_bytes": sample.disk_read_bytes,
        "disk_write_bytes": sample.disk_write_bytes,
    }


def _read_samples(path: Path, cls: type[Any]) -> list[Any]:
    if not path.exists():
        return []
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        samples.append(cls(**json.loads(line)))
    return samples
