# Configuration for deployment

## Pre-deployment checklist

- [ ] Install from a built wheel (see [Building a distribution](packaging.md))
- [ ] Set `DEBUG=False`
- [ ] Generate and set a strong unique `SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS` for your domain(s)
- [ ] Use a production database (PostgreSQL recommended; SQLite is fine for small/simple deployments)
- [ ] Set `POLYFILE_DATA_DIR` to a writable, persistent location
- [ ] Build/install production frontend assets (they are included in the wheel)
- [ ] Run `polyfile collectstatic --noinput` and configure static files serving
- [ ] Configure storage backends and media locations
- [ ] Run the deletion worker as a background service
- [ ] Set up HTTPS and secure cookies
- [ ] Review [Security](../system_core/security.md) requirements

## Environment variables

See [Environment variables](environment_variables.md) for all supported variables. At minimum for production:

```env
SECRET_KEY=<strong-random-key>
DEBUG=False
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
POLYFILE_DATA_DIR=/var/lib/polyfile
```

`POLYFILE_DATA_DIR` holds the SQLite database (unless `DATABASE_URL` is set), collected
static files, and media. It must be writable by the service user and must survive package
upgrades. See [Building a distribution](packaging.md#what-goes-where) for the layout.

## Database

The project uses `django-environ` with `DATABASE_URL`. By default it uses SQLite at
`<POLYFILE_DATA_DIR>/db.sqlite3`. For production, use PostgreSQL via `DATABASE_URL`:

```env
DATABASE_URL=postgres://user:password@host:5432/dbname
```

Install the appropriate driver (e.g., `psycopg`) into the application environment.

Run migrations:

```bash
polyfile migrate
# or, in a source checkout:
uv run python manage.py migrate
```

## Static files

- `STATIC_URL = 'static/'`
- `STATIC_ROOT` defaults to `<POLYFILE_DATA_DIR>/static`
- Run `polyfile collectstatic --noinput` after installation or upgrade
- Serve `STATIC_ROOT` via your web server (nginx/Apache) or a CDN

Do not use `site-packages` as `STATIC_ROOT` and do not run `collectstatic` into the
installed package.

## Frontend assets

Production assets are included in the wheel. To rebuild them from a source checkout:

```bash
cd frontend
npm run build
```

This outputs to `polyfile/web_assets/bundles/` and writes
`polyfile/webpack-stats.json`. `django-webpack-loader` reads the stats file when
`DEBUG=False`; ensure `WEBPACK_STATS_FILE` points to it if you override the default (see
[Environment variables](environment_variables.md)).

Development builds (`npm run build_dev` / `npm run watch`) go to `web_dev_assets/` and are
used only when `DEBUG=True`.

## Storage

Configure [FsStorage](../system_core/models_data_model.md#fsstorage) instances via Django
admin for each backend you want to use. Ensure directories/credentials are set up correctly
and have appropriate permissions.

Note that user files are stored under each storage's `root_path` from the database, not in
`MEDIA_ROOT`. `POLYFILE_DATA_DIR` does not move existing storage roots automatically.

## Background worker

[Recursive deletion](../system_core/recursive_deletion_background_jobs.md) requires a running worker. It is a
separate process — `runserver` and the production application server do not start it:

```bash
polyfile run_deletion_worker
# or, in a source checkout:
uv run python manage.py run_deletion_worker
```

Run this as a managed process (systemd, supervisor, Docker, etc.). Without it, deletions are accepted but never
completed.

## Security hardening

- Use HTTPS (`SECURE_SSL_REDIRECT`, HSTS)
- Set `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- Configure secure headers
- Keep dependencies updated
- Follow [Security](../system_core/security.md) guidelines

## Related docs

- [Installation & configuration](installation.md)
- [Building a distribution](packaging.md)
- [Environment variables](environment_variables.md)
- [Storage backends](../system_core/storage_backends.md)
- [Recursive deletion/background jobs](../system_core/recursive_deletion_background_jobs.md)
