manage = "./manage.py"
current_dir = $(shell pwd)

test:
	@python $(manage) test --noinput --failfast

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
