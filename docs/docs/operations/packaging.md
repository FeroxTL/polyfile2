# Building a distribution

Polyfile can be built as a standard Python `sdist`/`wheel` pair. The distributions contain
the Django project, templates, migrations, management commands, the production frontend
bundle, and the pre-built HTML documentation, so they can be installed and run without the
repository or Node.js.

## Prerequisites

- Python 3.11 or newer
- [uv](https://github.com/astral-sh/uv)
- Node.js and npm only when rebuilding the frontend

```bash
uv sync
```

`uv sync` installs the development tools used below, including `build` and `twine`.

## Build the frontend

The production build writes JavaScript and CSS to `polyfile/web_assets/` and the webpack
stats file to `polyfile/webpack-stats.json`:

```bash
cd frontend
npm ci
npm run build
cd ..
```

Use `npm run build_dev` or `npm run watch` for local development instead; those write to
`web_dev_assets/` and `webpack-dev-stats.json` and are not part of a distribution.

## Build the documentation

Documentation sources live in `docs/`, but the built HTML site is packaged into
`polyfile/docs/`:

```bash
uv run mkdocs build --strict --config-file ./docs/mkdocs.yml
```

`docs/` (the Markdown sources) is intentionally not included in distributions; only the
generated `polyfile/docs/` is shipped. The development server serves it at `/docs/` when
`DEBUG=True`; in production you can serve the same directory with your web server.

## Build the package

The canonical command is:

```bash
uv run python -m build
```

`uv build` is equivalent — both use the `hatchling` build backend declared in
`pyproject.toml`. A packaging hook fails the build with a clear message if the production
frontend assets, the webpack stats file, or `polyfile/docs/index.html` are missing.

Artifacts are written to `dist/`:

```text
dist/polyfile-0.1.0.tar.gz
dist/polyfile-0.1.0-py3-none-any.whl
```

The `sdist` contains the built frontend assets and the built documentation, so a wheel can
be produced from it without Node.js or MkDocs:

```bash
uv build --sdist
```

Set `POLYFILE_SKIP_FRONTEND_CHECK=1` or `POLYFILE_SKIP_DOCS_CHECK=1` only when you
deliberately need an artifact without the UI or without documentation.

## Verify the artifacts

```bash
uv run twine check dist/*
```

Inspect the wheel contents:

```bash
python -c "import zipfile; print('\n'.join(zipfile.ZipFile('dist/polyfile-0.1.0-py3-none-any.whl').namelist()))"
```

The wheel must contain, among others:

- `polyfile/core/templates/`
- `polyfile/apps/*/migrations/`
- `polyfile/apps/*/templates/`
- `polyfile/web_assets/bundles/`
- `polyfile/webpack-stats.json`
- `polyfile/docs/index.html`

It must not contain `frontend/node_modules`, the Markdown sources from `docs/`,
`__pycache__`, or a database.

## Install and run the wheel

```bash
uv venv .venv
uv pip install dist/polyfile-0.1.0-py3-none-any.whl
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Runtime state (SQLite database, collected static, media) belongs here:
export POLYFILE_DATA_DIR=/var/lib/polyfile

polyfile check
polyfile migrate
polyfile collectstatic --noinput
polyfile createsuperuser
polyfile runserver
```

On Windows the console script is `.venv\Scripts\polyfile.exe` and the environment variable
can be set with `$env:POLYFILE_DATA_DIR = "C:\path\to\data"`.

If the console script is not on `PATH`, run the same commands through the module:
`python -m polyfile check`, `python -m polyfile migrate`, and so on.

## What goes where

| Path                           | Purpose                                                                |
|--------------------------------|------------------------------------------------------------------------|
| `polyfile/`                    | Read-only package code and package data installed into `site-packages` |
| `polyfile/web_assets/`         | Production bundles inside the package                                  |
| `polyfile/webpack-stats.json`  | Bundle manifest used by `django-webpack-loader`                        |
| `polyfile/docs/`               | Pre-built HTML documentation (`/docs/` when `DEBUG=True`)              |
| `POLYFILE_DATA_DIR/db.sqlite3` | SQLite database (unless `DATABASE_URL` is set)                         |
| `POLYFILE_DATA_DIR/static/`    | Output of `collectstatic`                                              |
| `POLYFILE_DATA_DIR/media/`     | Default media root; actual file storage is configured per `FsStorage`  |

`docs/` and `frontend/` are source directories for the repository; they are not part of
the installed package.

Never run `collectstatic` into `site-packages`. Runtime data is kept outside the package so
that `pip install --upgrade` cannot overwrite it.

## Related commands

```bash
make assets      # install frontend deps and build production assets
make build-docs  # mkdocs build --strict into polyfile/docs/
make dist        # assets + docs + python -m build
make dist-check  # twine check
```
