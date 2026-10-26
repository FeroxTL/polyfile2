# Development workflow

## Environment setup

1. Clone repository
2. Install Python dependencies with `uv sync`
3. Install frontend dependencies in `frontend/` with `npm install`
4. Create `.env` file (see [Installation](../operations/installation.md))

5. Build frontend assets
6. Run migrations
7. Create superuser

## Development commands

### Backend
```bash
# Run development server
uv run python manage.py runserver

# Run migrations
uv run python manage.py migrate

# Create migrations
uv run python manage.py makemigrations

# Run tests
python manage.py test --noinput --failfast
# or via Makefile
make test

# Run deletion worker
uv run python manage.py run_deletion_worker
```

### Frontend
```bash
cd frontend

# Install dependencies
npm install

# Development build
npm run build_dev

# Watch mode
npm run watch

# Production build
npm run build

# Run tests
npm test

# Run tests with coverage
npm run test:coverage

# Lint
npx eslint .
```

### Code quality
```bash
# Lint with ruff
make ruff
# or
ruff check .

# Auto-fix
make ruff-fix
# or
ruff check . --fix

# Format check
make ruff-format

# Format
make ruff-format-fix
```

### Documentation
```bash
# Build docs
make build-docs
# or
uv run mkdocs build --config-file ./docs/mkdocs.yml
```

### Coverage
```bash
make coverage
```

## Coding standards

### Python
- Follow PEP 8
- Use type hints where possible, especially in `FsBackend` method signatures
- Use double quotes (`"`) for strings (project standard, transitioning from single quotes)
- Never use bare `except Exception:` - use specific exceptions
- Exceptions must provide clear, actionable messages
- Use specific exceptions: `PolyfileError`, `StorageBackendError`, or standard Django exceptions (`PermissionDenied`, `NotFoundError`)

### Naming conventions
- `FsNode` - Primary entity for files and directories
- `PurePosixPath` - Use `pathlib.PurePosixPath` for path manipulation
- `FsBackend` suffix for storage provider implementations (e.g., `S3FsBackend`)
- `FileSystemBackend` - Specific name for local/native filesystem backend

### Frontend
- Always use named exports for components (not default exports)
- Ensure ESLint compliance
- Follow existing Mithril.js patterns

## Agent roles (from AGENTS.md)
- **Backend/Storage Expert** - FileSystemBackend, storage providers, path manipulation, database operations for file metadata
- **Frontend/UI Expert** - SPA (Mithril.js), state management, UI reflecting FsNode structure with Bootstrap 5
- **Security Auditor** - Review mode for path traversal, IDOR, input sanitization

## Git workflow
- Work in feature branches
- Write tests for new features
- Update tests when changing code
- Run linting and tests before committing
- Follow commit message conventions
