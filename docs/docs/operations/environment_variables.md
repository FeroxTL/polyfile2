# Environment Variables

This document lists the environment variables read via `django-environ` in
`polyfile/core/settings.py`. A `.env` file is loaded from the current working directory by
default; use `POLYFILE_ENV_FILE` to point to another file.

## Core Django Settings

| Variable        | Type   | Default                                    | Description                                                                              |
|-----------------|--------|--------------------------------------------|------------------------------------------------------------------------------------------|
| `SECRET_KEY`    | `str`  | `django-insecure-string`                   | Secret key used for cryptographic signing. **Must be changed in production.**            |
| `DEBUG`         | `bool` | `True` if `runserver` is in `sys.argv`     | Enables debug mode. In production, set to `False` and configure `ALLOWED_HOSTS`.         |
| `ALLOWED_HOSTS` | `list` | `['localhost', '127.0.0.1']`               | List of allowed host/domain names. When `DEBUG=False`, this must be properly configured. |
| `DATABASE_URL`  | `str`  | `sqlite:///<POLYFILE_DATA_DIR>/db.sqlite3` | Database connection URL. Supports SQLite, PostgreSQL, MySQL, and others.                 |

## Runtime Paths

| Variable            | Type   | Default                      | Description                                                            |
|---------------------|--------|------------------------------|------------------------------------------------------------------------|
| `POLYFILE_DATA_DIR` | `path` | current working directory    | Root for the SQLite database, collected static files, and media.       |
| `POLYFILE_ENV_FILE` | `path` | `<cwd>/.env`                 | Path to the `.env` file loaded at startup.                             |
| `STATIC_ROOT`       | `path` | `<POLYFILE_DATA_DIR>/static` | Destination for `collectstatic`. Serve this directory in production.   |
| `MEDIA_ROOT`        | `path` | `<POLYFILE_DATA_DIR>/media`  | Default media root. Actual file storage is configured per `FsStorage`. |

Runtime data must stay outside `site-packages`; otherwise package upgrades can overwrite it
and the package directory may be read-only.

## Debug Toolbar

| Variable                | Type   | Default                                      | Description                                                                                                                   |
|-------------------------|--------|----------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| `DEBUG_TOOLBAR_ENABLED` | `bool` | `DEBUG` and `django-debug-toolbar` installed | Enables Django Debug Toolbar. When enabled, adds `debug_toolbar` to `INSTALLED_APPS` and inserts middleware at the beginning. |
| `INTERNAL_IPS`          | `list` | `['127.0.0.1']`                              | Internal IPs used by Django Debug Toolbar.                                                                                    |

The wheel does not depend on `django-debug-toolbar`, so `DEBUG_TOOLBAR_ENABLED=True` in an
installed package requires installing the development dependency explicitly.

## Webpack / Frontend Assets

| Variable             | Type         | Default                                                                                                                     | Description                                                                             |
|----------------------|--------------|-----------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------|
| `WEBPACK_STATS_FILE` | `str` (path) | `webpack-dev-stats.json` in the project root when `DEBUG=True` and the file exists, otherwise `polyfile/webpack-stats.json` | Path to the `webpack-bundle-tracker` stats file used by `django-webpack-loader`.        |
| `WEBPACK_ASSETS_DIR` | `str` (path) | `web_dev_assets/` in the project root when `DEBUG=True` and the directory exists, otherwise `polyfile/web_assets/`          | Directory containing built frontend assets. Added to `STATICFILES_DIRS` when it exists. |

## Notes

- Booleans are passed as `True`, `true`, `1`, `yes`.
- Lists are comma-separated (e.g., `127.0.0.1,localhost`).
- Database examples:
  - SQLite: `sqlite:///db.sqlite3` or `sqlite:////absolute/path/to/db.sqlite3`
  - PostgreSQL: `postgres://user:password@host:5432/dbname` (or `postgresql://...`)
  - MySQL/MariaDB: `mysql://user:password@host:3306/dbname`
- See [Configuration for deployment](configuration_for_deployment.md) for a production
  example.
