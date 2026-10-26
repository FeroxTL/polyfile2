# Environment Variables

This document lists all environment variables read from the `.env` file via `django-environ` in `polyfile/core/settings.py`.

## Core Django Settings

| Variable        | Type   | Default                             | Description                                                                              |
|-----------------|--------|-------------------------------------|------------------------------------------------------------------------------------------|
| `SECRET_KEY`    | `str`  | `django-insecure-string`            | Secret key used for cryptographic signing. **Must be changed in production.**            |
| `DEBUG`         | `bool` | `True` if "runserver" in sys.argv | Enables debug mode. In production, set to `False` and configure `ALLOWED_HOSTS`.         |
| `ALLOWED_HOSTS` | `list` | `['localhost', '127.0.0.1']`        | List of allowed host/domain names. When `DEBUG=False`, this must be properly configured. |
| `DATABASE_URL`  | `str`  | `sqlite:///<BASE_DIR>/db.sqlite3`   | Database connection URL. Supports SQLite, PostgreSQL, MySQL, and others via `django-environ`. |

## Debug Toolbar

| Variable                | Type   | Default         | Description                                                                                                                   |
|-------------------------|--------|-----------------|-------------------------------------------------------------------------------------------------------------------------------|
| `DEBUG_TOOLBAR_ENABLED` | `bool` | `DEBUG`         | Enables Django Debug Toolbar. When enabled, adds `debug_toolbar` to `INSTALLED_APPS` and inserts middleware at the beginning. |
| `INTERNAL_IPS`          | `list` | `['127.0.0.1']` | Internal IPs used by Django Debug Toolbar.                                                                                    |

## Webpack / Frontend Assets

| Variable             | Type         | Default                                                                                   | Description                                                                      |
|----------------------|--------------|-------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|
| `WEBPACK_STATS_FILE` | `str` (path) | `webpack-dev-stats.json` in `ROOT_DIR` if `DEBUG` else `webpack-stats.json` in `BASE_DIR` | Path to the `webpack-bundle-tracker` stats file used by `django-webpack-loader`. |
| `WEBPACK_ASSETS_DIR` | `str` (path) | `web_dev_assets/` in `ROOT_DIR` if `DEBUG` else `polyfile/web_assets/` in `BASE_DIR`      | Directory containing built frontend assets. Added to `STATICFILES_DIRS`.         |

## Notes

- Environment variables are loaded from the `.env` file in the current working directory via `environ.Env.read_env(Path.cwd() / '.env')`.
- Booleans are passed as `True`, `true`, `1`, `yes`.
- Lists are comma-separated (e.g., `127.0.0.1,localhost`).
- Database examples:
  - SQLite: `sqlite:///db.sqlite3` or `sqlite:////absolute/path/to/db.sqlite3`
  - PostgreSQL: `postgres://user:password@host:5432/dbname` (or `postgresql://...`)
  - MySQL/MariaDB: `mysql://user:password@host:3306/dbname`
