import subprocess
import sys
from pathlib import Path


def test_ruff_linting() -> None:
    """Run ruff to check for linting errors in the project."""
    project_root = Path(__file__).resolve().parents[3]

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(project_root)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"Ruff found linting issues:\n{result.stdout}"
