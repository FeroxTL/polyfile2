# Configuration for deployment

## Pre-deployment checklist

- [ ] Set `DEBUG=False`
- [ ] Generate and set a strong unique `SECRET_KEY`
- [ ] Configure `ALLOWED_HOSTS` for your domain(s)
- [ ] Use a production database (PostgreSQL recommended; SQLite is fine for small/simple deployments)
- [ ] Build frontend assets for production
- [ ] Configure static files serving
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
```

Note: In the current codebase, `ALLOWED_HOSTS` may be influenced by settings; ensure it's properly configured for your deployment.

## Database

The project uses `django-environ` with `DATABASE_URL`. By default it uses SQLite (`db.sqlite3`). For production, use PostgreSQL via `DATABASE_URL`:

```env
DATABASE_URL=postgres://user:password@host:5432/dbname
```

You can also set individual variables as before, but `DATABASE_URL` is the recommended approach. Install the appropriate driver (e.g., `psycopg`).

Run migrations: `python manage.py migrate`

## Static files

- `STATIC_URL = 'static/'`
- `STATIC_ROOT` is configured in settings
- Run `python manage.py collectstatic` after building assets
- Serve static files via your web server (nginx/Apache) or CDN

## Frontend assets

For production builds:

```bash
cd frontend
npm run build
```

This outputs to `polyfile/web_assets/bundles/`. Ensure `WEBPACK_STATS_FILE` points to the correct stats file (see [Environment variables](environment_variables.md)) and `django-webpack-loader` can find it.

## Storage

Configure [FsStorage](../system_core/models_data_model.md#fsstorage) instances via Django admin for each backend you want to use. Ensure directories/credentials are set up correctly and have appropriate permissions.

## Background worker

[Recursive deletion](../system_core/recursive_deletion_background_jobs.md) requires a running worker:
```bash
uv run python manage.py run_deletion_worker
```

Run this as a managed process (systemd, supervisor, Docker, etc.).

## Security hardening

- Use HTTPS (`SECURE_SSL_REDIRECT`, HSTS)
- Set `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`
- Configure secure headers
- Keep dependencies updated
- Follow [Security](../system_core/security.md) guidelines

## Related docs

- [Installation & configuration](../installation/installation.md)
- [Environment variables](../environment_variables.md)
- [Storage backends](../system_core/storage_backends.md)
- [Recursive deletion/background jobs](../system_core/recursive_deletion_background_jobs.md)
