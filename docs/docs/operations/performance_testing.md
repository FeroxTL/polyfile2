# Performance testing

Polyfile ships a separate load-testing harness in `test_suites/perf_tests/` at the repository
root. It is intentionally not part of the `polyfile` package and is not
installed as a runtime dependency.

## Scope

The current harness targets **SQLite** deployments and covers the main file
management API. PostgreSQL tuning, pagination and live graphs are out of scope
for this version. Results are written as a static HTML report after each run.

## Components

- `test_suites/perf_tests/polyfile_test_suites/perf_tests/client.py` — synchronous `httpx` client for the JSON API.
- `test_suites/perf_tests/polyfile_test_suites/perf_tests/smoke.py` — end-to-end smoke flow.
- `test_suites/perf_tests/polyfile_test_suites/perf_tests/scenarios.py` — locust user and tasks (`read`, `write`,
  `share` tags).
- `test_suites/perf_tests/polyfile_test_suites/perf_tests/quota.py` — disk-usage guard.
- `test_suites/perf_tests/polyfile_test_suites/perf_tests/metrics.py` — request and machine-resource sampling.
- `test_suites/perf_tests/polyfile_test_suites/perf_tests/report.py` — self-contained HTML report.

## Setup

```bash
cd perf
uv sync --extra dev
```

Create a key for a dedicated test user:

```bash
uv run python manage.py create_api_key --username perf-user --name load-test --json
export POLYFILE_API_KEY='pf_...'
```

The harness authenticates exactly like any other API client, using
`Authorization: Bearer <token>` (see
[Authentication & accounts](../system_core/authentication_accounts.md#api-keys)).

Start the server and a deletion worker (the smoke flow waits for asynchronous
deletion jobs, and load runs schedule many of them):

```bash
uv run python manage.py runserver 127.0.0.1:8000
uv run python manage.py run_deletion_worker
```

## Commands

| Command | Purpose |
| --- | --- |
| `uv run polyfile-perf check` | Verify quota limits and API authentication |
| `uv run polyfile-perf smoke` | Run the end-to-end API smoke flow |
| `uv run polyfile-perf run --profile read` | Run a locust scenario |
| `uv run polyfile-perf profiles` | List built-in load profiles |
| `uv run polyfile-perf report <run-dir>` | Rebuild a report from artifacts |

Built-in profiles: `smoke`, `read`, `write`, `mixed`. Override `--users`,
`--spawn-rate` and `--duration` per run.

## Disk-usage guard

Load tests create files and archives. The guard only **observes** directories;
it never deletes data. If a configured limit is crossed, the run aborts before
the disk can fill up:

```toml
[quota]
enabled = true
data_dir = "local"
max_temp_bytes = "512MB"
max_archive_bytes = "1GB"
max_total_bytes = "2GB"
min_free_bytes = "2GB"
poll_interval = 5.0
```

By default it watches `<data_dir>/tmp`, `<data_dir>/archives` and the data
directory itself. Set `quota.temp_dir` to the server's `TMPDIR`/`TEMP` if large
uploads spill there. The same guard runs before the smoke flow and during
locust runs.

## Output

Each run creates a timestamped directory under `test_suites/perf_tests/runs/` (git-ignored):

- `report.html` — self-contained report with latency, throughput, status codes,
  resource usage and quota state.
- `summary.json` — configuration and aggregate metrics.
- `requests.jsonl` — per-request samples (smoke runs).
- `resources.jsonl` — CPU, memory and disk I/O samples.
- `locust*.csv` — raw locust statistics (load runs).

## Configuration

Defaults live in `test_suites/perf_tests/perf.toml`. Environment variables:

| Variable | Purpose |
| --- | --- |
| `POLYFILE_API_KEY` | API key used by the harness |
| `POLYFILE_PERF_CONFIG` | Alternative TOML config path |
| `POLYFILE_PERF_BASE_URL` | Override the target base URL |
| `POLYFILE_PERF_OUTPUT_DIR` | Override the output directory |
| `POLYFILE_DATA_DIR` | Data directory used by the quota guard |

## Tests

```bash
cd perf
uv run pytest
uv run ruff check .
```

The harness tests use `httpx.MockTransport` and temporary directories, so they
do not require a running Polyfile instance.
