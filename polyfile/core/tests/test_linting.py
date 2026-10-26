import subprocess
import unittest


def test_ruff_linting() -> None:
    """
    Run ruff to check for linting errors in the project.
    """
    # The path to the project root as specified by the user
    project_root = r"C:\Users\ferox\PycharmProjects\polyfile2\polyfile"

    # Run ruff check on the project root
    # We use 'ruff' command. If it's not in the PATH, this might fail.
    # The user said ruff is already installed.
    result = subprocess.run(
        ["ruff", "check", project_root],
        check=False,
        capture_output=True,
        text=True
    )

    # ruff check returns 0 if no errors are found, and a non-zero value if errors are found.
    # If ruff is not found, returncode will be non-zero (usually 127 or similar).
    if result.returncode == 127:
        # This usually means the 'ruff' command was not found.
        # We can provide a helpful message.
        raise RuntimeError("The 'ruff' command was not found in the PATH. Please ensure it is installed and accessible.")

    assert result.returncode == 0, f"Ruff found linting issues:\n{result.stdout}"
