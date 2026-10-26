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

## Test organization
- Backend tests typically in `tests.py` or `tests/` directories within apps
- Frontend tests alongside components or in `__tests__` directories
- Use factories for model instances
- Mock external dependencies when appropriate
