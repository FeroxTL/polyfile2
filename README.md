# Polyfile - Custom Storage Solution

Polyfile is a Django-based project designed to provide flexible file storage solutions with support for user accounts.
It offers modular architecture for integrating various storage backends and managing files efficiently.

# Current status

Proof-of-works. Nothing works stable, use at your own risk.

## Overview

Polyfile combines Django's robust framework with customizable storage capabilities,
allowing users to manage their files through both web interfaces and RESTful APIs.
The application supports multiple storage backends (e.g., local file system and S3)
and integrates seamlessly with Django’s built-in authentication system.

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
media) is stored in `POLYFILE_DATA_DIR` (the current directory by default).

See the [documentation](docs/docs/index.md) for configuration, deployment, and packaging
details.

## Roadmap

The roadmap and current status are maintained in the documentation:
[docs/docs/contributors/roadmap.md](docs/docs/contributors/roadmap.md).

The README intentionally does not duplicate it, so there is a single source of truth for
what is planned and what has already shipped.

