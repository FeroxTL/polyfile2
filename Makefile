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
	mkdocs build --config-file ./docs/mkdocs.yml

coverage:
	@coverage erase
	@coverage run $(manage) test --noinput --failfast
	@coverage html --skip-covered
	@echo
	@echo
	@echo "Coverage:" "file://"$(current_dir)"/local/htmlcov/index.html"
