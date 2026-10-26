# Installation and Configuration

## Prerequisites

To run this project, you need:

- [Python 3.11](https://www.python.org/) or higher
- [uv](https://github.com/astral-sh/uv) — a modern and fast Python package manager
- [Node.js](https://nodejs.org/) and [npm](https://www.npmjs.com/) for building the frontend assets

## Backend Installation

1. **Clone the repository:**
```bash
git clone <REPOSITORY_URL>
cd polyfile2
```

2. **Install Python dependencies:**
Use `uv` to create a virtual environment and install dependencies:
```bash
uv sync
```

## Frontend Installation and Build

The frontend is located in the `frontend/` directory. Webpack builds the assets into `web_dev_assets/` (development) or `polyfile/web_assets/` (production).

1. **Install frontend dependencies:**
```bash
cd frontend
npm install
```

2. **Build frontend assets:**

- **Development build** (outputs to `../web_dev_assets/bundles/`, used when `DEBUG=True`):
```bash
npm run build_dev
```
- **Development build with watch mode** (auto-rebuild on changes):
```bash
npm run watch
```
- **Production build** (outputs to `../polyfile/web_assets/bundles/`):
```bash
npm run build
```

After building, return to the project root directory before running Django commands.

## Environment Configuration

Create a `.env` file in the root directory of the project (`polyfile2/`) with the necessary environment variables. 

### Minimal working configuration

```env
SECRET_KEY=change-this-to-a-unique-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DEBUG_TOOLBAR_ENABLED=True
```

### Notes

- `SECRET_KEY` must be changed in production. If not set, a default development key is used (not safe for production). Generate a strong unique key with:
  ```bash
  python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
  ```
- `DEBUG` defaults to `True` when running via `runserver`, but it is recommended to explicitly set it.
- `ALLOWED_HOSTS` is required when `DEBUG=False`.
- `DEBUG_TOOLBAR_ENABLED` enables Django Debug Toolbar when `True` and `DEBUG` is `True`.
- See [Environment Variables](environment_variables.md) for a full list of all supported variables.

## Database Initialization

The project uses `django-environ` with `DATABASE_URL`. By default it uses SQLite at `db.sqlite3` in the project base directory. To use a different database (PostgreSQL, MySQL, etc.), set `DATABASE_URL` in your `.env` file (see [Environment Variables](environment_variables.md#core-django-settings)) and install the required database driver.

After installing dependencies and configuring the `.env` file, apply database migrations:

```bash
uv run python manage.py migrate
```

Create a superuser to access the Django admin panel:

```bash
uv run python manage.py createsuperuser
```

## Running the Project

1. **Build the frontend** (see [Frontend Installation and Build](#frontend-installation-and-build)) if you haven't already.
2. **Start the deletion worker:**
3. `uv run python manage.py run_deletion_worker`
  This worker processes asynchronous [recursive deletion jobs](../system_core/recursive_deletion_background_jobs.md) created when nodes are deleted via the API. It must be running in the background for file/directory deletions to be completed.
4. **Start the development server:**
```bash
uv run python manage.py runserver
```
5. Open `http://127.0.0.1:8000` in your browser.

## Building Documentation

To build the project documentation using MkDocs:

```bash
uv run mkdocs build --config-file ./docs/mkdocs.yml
```

Or using the Makefile:

```bash
make build-docs
```
