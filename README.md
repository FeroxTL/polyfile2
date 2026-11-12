# Polyfile - Custom Storage Solution

Polyfile is a Django-based project designed to provide flexible file storage solutions with support for user accounts.
It offers modular architecture for integrating various storage backends and managing files efficiently.

## Current status

Early-stage proof of work. Nothing is stable yet; use at your own risk. See the
[Roadmap](docs/docs/contributors/roadmap.md) for what is planned.

## Overview

Polyfile combines Django's robust framework with customizable storage capabilities,
allowing users to manage their files through both web interfaces and RESTful APIs.
It currently ships a local filesystem backend and is designed for additional backends
such as S3, and it integrates with Django's built-in authentication system.

## Features

- **User Authentication**: Built on top of Django's user model for secure account management.
- **Custom Storage Backends**: Supports various storage solutions, including local path-based storage.
- **File Management API**: RESTful endpoints for uploading, listing, and managing files.

## Installation

### From source (development)

```bash
uv sync
cd frontend
npm install
npm run build_dev
# or `npm run watch`
cd ..
```

Create a `.env` file, then run:

```bash
uv run python manage.py migrate
uv run python manage.py runserver

# in a second terminal — runserver does not start this worker
uv run python manage.py run_deletion_worker
```

Recursive deletion is handled by the background worker. Without it, deletion jobs are accepted but stay pending.

## Testing

### Unit and integration tests

```bash
# Django backend tests
uv run python manage.py test --noinput --failfast

# Frontend unit tests with vitest
cd frontend
npm run test:coverage
```

### Browser end-to-end tests

E2E tests run a real Chromium browser against a live Django server. They live in
`test_suites/browser_tests/` and use `pytest-playwright` + `pytest-django` with the dedicated
`polyfile.core.settings_e2e` settings module.

First, install the Playwright browser binaries (one-time):

```bash
uv run playwright install chromium
```

Run the full E2E suite (rebuilds production frontend assets automatically):

```bash
make e2e
# or directly:
uv run pytest test_suites/browser_tests -v --browser chromium
```

For faster local iteration when frontend assets are already built:

```bash
make e2e-fast
# or directly:
set SKIP_FRONTEND_BUILD=1 && uv run pytest test_suites/browser_tests -v --browser chromium
```

Run a single test file:

```bash
uv run pytest test_suites/browser_tests/test_login.py -v --browser chromium
```

Run with a visible browser window (headed mode):

```bash
uv run pytest test_suites/browser_tests -v --browser chromium --headed
```

### From a wheel

```bash
cd frontend
npm ci
npm run build
cd ..

uv run mkdocs build --strict --config-file ./docs/mkdocs.yml
uv run python -m build   # or: uv build
uv venv .venv
uv pip install dist/polyfile-0.1.0-py3-none-any.whl
POLYFILE_DATA_DIR=./data .venv/bin/polyfile migrate
POLYFILE_DATA_DIR=./data .venv/bin/polyfile runserver  # development only!

# in a second terminal — runserver does not start this worker
POLYFILE_DATA_DIR=./data .venv/bin/polyfile run_deletion_worker
```

The wheel includes the production frontend assets and the pre-built HTML documentation and
does not require Node.js or MkDocs. Runtime data (SQLite database, collected static files,
media, and directory archives) is stored in `POLYFILE_DATA_DIR` (`./local` by default).

See the [documentation](docs/docs/index.md) for configuration, deployment, and packaging
details.

## Roadmap and release notes

- [Roadmap](docs/docs/contributors/roadmap.md) — what is planned, including the next release.
- [Release notes](docs/docs/releases/index.md) — the only history of changes, including the current release journal.

### How to keep them up to date

- **Roadmap:** add only future work. Keep the next release short and move items out as soon
  as they ship. Do not keep lists of released versions here.
- **Release journal:** while working, add every user-visible change to
  `docs/docs/releases/next.md` under `Added`, `Changed`, `Fixed` or `Security`. Keep the
  highlights and upgrade notes current as you go.
- **At release:** rename `next.md` to `<version>.md`, set its status and date, finalize the
  upgrade notes, add the version to `docs/docs/releases/index.md` and `docs/mkdocs.yml`,
  create a fresh `next.md`, and update links to point at the new version page. Remove
  shipped items from the roadmap, bump the version in `pyproject.toml`, tag the release, and
  publish the same notes as a GitHub Release.
- Do not copy the roadmap or release history into the README — link to the single source.

