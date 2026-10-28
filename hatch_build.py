"""Hatchling build hook that validates packaged static artifacts.

Why this hook exists
--------------------
The production frontend bundle and the built documentation are generated
artifacts: they are ignored by git, but they must be shipped inside the
distributions. If they are simply missing, Hatchling would still produce a
wheel successfully, but the installed application would have no CSS/JS or no
``/docs/`` page. This hook turns that silent failure into an early, actionable
build error.

Where it is used
----------------
The hook is enabled in ``pyproject.toml``::

    [tool.hatch.build.targets.wheel.hooks.custom]

Hatchling discovers ``hatch_build.py`` in the project root, imports
``FrontendAssetsBuildHook`` (matched by ``PLUGIN_NAME = "custom"``) and calls
``initialize()`` before assembling the wheel. The hook also runs when a wheel is
built from the sdist, so this file must be included in the sdist as well.

What is validated
-----------------
- ``polyfile/webpack-stats.json`` exists, is valid JSON and contains completed
  webpack stats (``status == "done"`` and a non-empty ``chunks`` list).
- ``polyfile/web_assets/bundles/`` contains at least one JavaScript bundle.
- ``polyfile/docs/index.html`` exists.

The hook does not build anything; it only verifies that the artifacts are
present. Generate them first::

    cd frontend && npm ci && npm run build
    uv run mkdocs build --strict --config-file ./docs/mkdocs.yml
    uv run python -m build

or run ``make dist``, which performs all three steps in order.

Editable installs are skipped because they use the development assets in
``web_dev_assets/``. For deliberate source-only artifacts, the checks can be
disabled with ``POLYFILE_SKIP_FRONTEND_CHECK=1`` and/or
``POLYFILE_SKIP_DOCS_CHECK=1``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class FrontendAssetsBuildHook(BuildHookInterface):
    """Validate generated frontend and documentation artifacts before packaging."""

    PLUGIN_NAME = "custom"

    def initialize(self, version: str, build_data: dict) -> None:
        """Run validation before Hatchling assembles the wheel."""
        # Editable installs run from a source checkout and use web_dev_assets/,
        # so production artifacts are not required for them.
        if version == "editable":
            return

        if os.environ.get("POLYFILE_SKIP_FRONTEND_CHECK") == "1":
            return

        project_root = Path(self.root)
        stats_file = project_root / "polyfile" / "webpack-stats.json"
        bundles_dir = project_root / "polyfile" / "web_assets" / "bundles"

        if not stats_file.is_file():
            raise RuntimeError(
                "Production frontend stats were not found at "
                f"{stats_file}. Run `npm run build` in frontend/ "
                "(or `make assets`) before building the package. "
                "Set POLYFILE_SKIP_FRONTEND_CHECK=1 only for source-only builds."
            )

        if not any(bundles_dir.glob("*.js")):
            raise RuntimeError(
                "Production frontend bundles were not found at "
                f"{bundles_dir}. Run `npm run build` in frontend/ "
                "(or `make assets`) before building the package. "
                "Set POLYFILE_SKIP_FRONTEND_CHECK=1 only for source-only builds."
            )

        if os.environ.get("POLYFILE_SKIP_DOCS_CHECK") != "1":
            docs_index = project_root / "polyfile" / "docs" / "index.html"
            if not docs_index.is_file():
                raise RuntimeError(
                    "Built documentation was not found at "
                    f"{docs_index}. Run `make build-docs` (or `uv run mkdocs build "
                    "--strict --config-file ./docs/mkdocs.yml`) before building "
                    "the package. Set POLYFILE_SKIP_DOCS_CHECK=1 to build "
                    "without documentation."
                )

        try:
            stats = json.loads(stats_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Invalid webpack stats file {stats_file}: {exc}"
            ) from exc

        if stats.get("status") != "done" or not stats.get("chunks"):
            raise RuntimeError(
                f"Webpack stats file {stats_file} is incomplete. "
                "Rebuild the production frontend with `npm run build`."
            )
