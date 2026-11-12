# Polyfile performance harness

A separate load-testing project for Polyfile. It is intentionally **not** part
of the `polyfile` package or its runtime dependencies.

## What it does

- **Smoke run** — exercises the main API flow end to end with a real API key:
  dashboard probe, root listing, mkdir, touch, upload, listing check, share
  create/detail/revoke, and asynchronous delete with job polling.
- **Load run** — drives the same flows with [Locust](https://locust.io/),
  records machine resource usage, and writes a static HTML report.
- **Quota guard** — observes temp/archive/data directory sizes and aborts a run
  when configured limits are exceeded. It never deletes files itself.

PostgreSQL, pagination and live graphs are out of scope for this first version.

## Setup

```bash
cd test_suites/perf_tests
uv sync --extra dev
```

Create an API key for a test user in the main project:

```bash
uv run python manage.py create_api_key --username perf-user --name load-test --json
```

Export the token (the harness reads it from `POLYFILE_API_KEY`):

```bash
export POLYFILE_API_KEY='pf_...'
```

Start Polyfile (SQLite is fine for the current target):

```bash
uv run python manage.py runserver 127.0.0.1:8000
```

The smoke flow waits for asynchronous deletion jobs to finish, so a deletion
worker must be running against the same database:

```bash
uv run python manage.py run_deletion_worker
```

## Usage

```bash
# Preflight: quota limits + API authentication
uv run polyfile-perf check

# End-to-end smoke flow
uv run polyfile-perf smoke

# Short locust run using the built-in "smoke" profile
uv run polyfile-perf run --profile smoke

# Read-heavy run for 60 seconds
uv run polyfile-perf run --profile read --duration 1m

# List profiles
uv run polyfile-perf profiles

# Rebuild the HTML report for an existing run directory
uv run polyfile-perf report runs/smoke-20260101T120000Z
```

Every run writes a directory under `test_suites/perf_tests/runs/` (git-ignored):

```
runs/<run>/
  report.html        # self-contained report (plotly.js embedded)
  summary.json       # configuration, aggregate metrics, quota state
  requests.jsonl     # per-request samples
  resources.jsonl    # CPU / memory / disk I/O samples
  locust*.csv        # raw locust statistics for load runs
```

## Configuration

Defaults live in `test_suites/perf_tests/perf.toml`; CLI flags override them. Environment
variables:

| Variable | Purpose |
| --- | --- |
| `POLYFILE_API_KEY` | API key used by smoke and locust runs |
| `POLYFILE_PERF_CONFIG` | Alternative TOML config path |
| `POLYFILE_PERF_BASE_URL` | Override `target.base_url` |
| `POLYFILE_PERF_OUTPUT_DIR` | Override the output directory |
| `POLYFILE_DATA_DIR` | Polyfile data dir used by the quota guard |

The quota guard defaults to watching `<repo>/local/tmp`,
`<repo>/local/archives` and `<repo>/local`. Set `quota.temp_dir` to the server's
`TMPDIR`/`TEMP` if uploads spill there.

## Tests

```bash
cd test_suites/perf_tests
uv run pytest
```

Tests use `httpx.MockTransport` and temporary directories, so no running server
is required.
