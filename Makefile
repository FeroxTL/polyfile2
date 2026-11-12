manage = "./manage.py"
current_dir = $(shell pwd)

.PHONY: test e2e e2e-fast perf-test perf-lint perf-smoke

test:
	@python $(manage) test --noinput --failfast

e2e:
	@uv run pytest test_suites/browser_tests -v --browser chromium

e2e-fast:
	@set SKIP_FRONTEND_BUILD=1 && uv run pytest test_suites/browser_tests -v --browser chromium

ruff:
	@ruff check .

ruff-fix:
	@ruff check . --fix

ruff-format:
	@ruff format . --check

ruff-format-fix:
	@ruff format .

build-docs:
	uv run mkdocs build --strict --config-file ./docs/mkdocs.yml

assets:
	cd frontend && npm ci && npm run build

dist: assets build-docs
	uv run python -m build

dist-check:
	uv run twine check dist/*

coverage:
	@coverage erase
	@coverage run $(manage) test --noinput --failfast
	@coverage html --skip-covered
	@echo
	@echo
	@echo "Coverage:" "file://"$(current_dir)"/local/htmlcov/index.html"

perf-test:
	cd test_suites/perf_tests && uv run pytest

perf-lint:
	cd test_suites/perf_tests && uv run ruff check .

perf-smoke:
	cd test_suites/perf_tests && uv run polyfile-perf smoke
