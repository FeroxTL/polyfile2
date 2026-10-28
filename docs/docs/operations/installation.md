# Installation and Configuration

## Prerequisites

- [Python 3.11](https://www.python.org/) or newer
- [uv](https://github.com/astral-sh/uv) — a modern and fast Python package manager
- [Node.js](https://nodejs.org/) and [npm](https://www.npmjs.com/) only for building or
  changing the frontend

On macOS, `python-magic` also requires the `libmagic` library (for example,
`brew install libmagic`).

There are two installation paths:

- **from source** — for development and for building a distribution;
- **from a wheel** — for running a packaged release without the repository.

## Installing from source (development)

1\. ** Clone the repository:**

```bash
git clone <REPOSITORY_URL>
cd polyfile2
```

2\. **Install Python dependencies:**

```bash
uv sync
```

3\. **Install and build the frontend:**

```bash
cd frontend
npm install
npm run build_dev
cd ..
```

`npm run build_dev` writes development assets to `web_dev_assets/`. Use `npm run watch`
while working on the frontend. For a production build use `npm run build`; see
[Building a distribution](packaging.md).

4\. **Create a `.env` file** in the project root (see [Environment Configuration](#environment-configuration)).

5\. **Apply migrations and create an administrator:**

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
```

6\. **Start the development server:**

```bash
uv run python manage.py runserver
```

7\. **Start the deletion worker in a second terminal:**

```bash
uv run python manage.py run_deletion_worker
```

`runserver` does not start the worker. Without it, recursive deletion jobs are accepted but remain pending and
their files are not physically removed. See [Background Worker](#background-worker) for details.

Open `http://127.0.0.1:8000` in a browser.

## Installing from a wheel

Build the wheel as described in [Building a distribution](packaging.md), then install it
into a clean environment:

```bash
uv venv .venv
uv pip install dist/polyfile-0.1.0-py3-none-any.whl
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

The package provides the `polyfile` console script. It includes the production frontend
assets, so Node.js is not required.

```bash
polyfile check
polyfile migrate
polyfile collectstatic --noinput
polyfile createsuperuser
polyfile runserver
```

Runtime state is stored in `POLYFILE_DATA_DIR` (the current working directory by default):

```text
<POLYFILE_DATA_DIR>/
  db.sqlite3
  static/
  media/
```

Set it explicitly for production:

```env
POLYFILE_DATA_DIR=/var/lib/polyfile
```

`collectstatic` copies package assets into `<POLYFILE_DATA_DIR>/static/`; the package
directory itself is never written to.

## Environment Configuration

Create a `.env` file in the working directory from which Polyfile is started, or point
`POLYFILE_ENV_FILE` to a different file.

### Minimal working configuration

```env
SECRET_KEY=change-this-to-a-unique-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Notes

- `SECRET_KEY` must be changed in production. If it is not set, an insecure development
  key is used.
- `DEBUG` defaults to `True` when the process is started with `runserver`.
- `ALLOWED_HOSTS` is required when `DEBUG=False`.
- `DEBUG_TOOLBAR_ENABLED` enables Django Debug Toolbar. It is enabled by default when
  `DEBUG=True` and `django-debug-toolbar` is installed; the development dependency is not
  part of the wheel.
- `POLYFILE_DATA_DIR` controls where the database, collected static files, and media live.
- `DATABASE_URL` overrides the default SQLite database; see
  [Environment Variables](environment_variables.md) for all supported variables.

## Database Initialization

The project uses `django-environ` with `DATABASE_URL`. By default it uses SQLite at
`<POLYFILE_DATA_DIR>/db.sqlite3`. To use PostgreSQL or another database, set
`DATABASE_URL` in `.env` and install the driver:

```env
DATABASE_URL=postgres://user:password@host:5432/dbname
```

```bash
uv pip install "psycopg[binary]>=3.2"
```

Apply migrations:

```bash
polyfile migrate
# or, in a source checkout:
uv run python manage.py migrate
```

## Background Worker

Recursive deletion uses a background worker. It is a separate process: `runserver` does not start it, and it
must be running in development as well as in production. Keep it running as a managed process:

```bash
polyfile run_deletion_worker
# or, in a source checkout:
uv run python manage.py run_deletion_worker
```

Without the worker, `DELETE` requests still return `202 Accepted`, but the jobs stay pending and the files are
not removed.

See [Recursive deletion/background jobs](../system_core/recursive_deletion_background_jobs.md)
for details.

## Building Documentation

```bash
uv run mkdocs build --strict --config-file ./docs/mkdocs.yml
```

Or via the Makefile:

```bash
make build-docs
```

The output is written to `polyfile/docs/` and packaged with distributions. The development
server serves it at `/docs/` when `DEBUG=True`; in production serve the directory with your
web server.
