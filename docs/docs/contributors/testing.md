# Testing

## Testing standards

- **Mandatory**: Every new feature must include tests. Existing tests must be updated/fixed when code changes
- Use `factory-boy` for dynamic fixture creation
- Use file-based fixtures for large, static datasets where appropriate

## Backend testing

### Tools
- `django.test` and `unittest`
- `factory-boy` for fixtures
- `coverage` for coverage reporting

### Running tests
```bash
# Run all tests
python manage.py test --noinput --failfast

# Via Makefile
make test

# With coverage
make coverage
# or
coverage run manage.py test --noinput --failfast
coverage html
```

### Coverage
- Backend: Run `coverage run manage.py test` to ensure high test coverage
- Coverage reports go to `local/htmlcov/` (see Makefile)

## Frontend testing

### Tools
- `vitest` for unit and integration tests
- `@vitest/coverage-v8` for coverage

### Running tests
```bash
cd frontend

# Run tests
npm test

# Run with coverage
npm run test:coverage
```

Frontend coverage target: high test coverage as per AGENTS.md.

## Browser end-to-end testing

### Tools

- `pytest-playwright` for driving a real browser
- `pytest-django` and its `live_server` fixture for the test Django server
- Dedicated settings module: `polyfile.core.settings_e2e`

Tests live in `test_suites/browser_tests/` and are **not** part of the regular Django test runner. They spin up a live server, build production frontend assets, and execute real user workflows in Chromium.

### Running tests

```bash
# One-time: install the Chromium binary for Playwright
uv run playwright install chromium

# Full E2E suite (rebuilds frontend assets automatically)
uv run pytest test_suites/browser_tests -v --browser chromium

# Via Makefile
make e2e

# Fast local iteration: skip the frontend build if assets are already up to date
make e2e-fast
# or directly
SKIP_FRONTEND_BUILD=1 uv run pytest test_suites/browser_tests -v --browser chromium

# Run a single test file
uv run pytest test_suites/browser_tests/test_login.py -v --browser chromium

# Run with a visible browser window
uv run pytest test_suites/browser_tests/ -v --browser chromium --headed

# Generate a Playwright trace for debugging
uv run pytest test_suites/browser_tests/ -v --browser chromium --tracing on
```

### E2E test structure

- `test_suites/browser_tests/conftest.py` — shared fixtures: temporary `POLYFILE_DATA_DIR`, frontend build, Django settings overrides, authenticated page.
- `test_suites/browser_tests/pages/` — Page Objects (`LoginPage`, `DashboardPage`, `PublicSharePage`).
- `test_suites/browser_tests/test_*.py` — scenario tests covering login, navigation, directory creation, file upload, public sharing, and deletion.

### What is covered

| Scenario | Test file |
|----------|-----------|
| Login and redirect to `/files/` | `test_suites/browser_tests/test_login.py` |
| Browse root, create and open directories | `test_suites/browser_tests/test_navigation.py` |
| Upload a file | `test_suites/browser_tests/test_upload.py` |
| Create and open a public share | `test_suites/browser_tests/test_share.py` |
| Delete a directory | `test_suites/browser_tests/test_delete.py` |

## Test organization
- Backend tests typically in `tests.py` or `tests/` directories within apps
- Frontend tests alongside components or in `__tests__` directories
- Use factories for model instances
- Mock external dependencies when appropriate
