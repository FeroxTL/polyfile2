import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class CliTests(SimpleTestCase):
    def test_python_m_polyfile_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env["POLYFILE_DATA_DIR"] = tmp_dir
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
            )

            result = subprocess.run(
                [sys.executable, "-m", "polyfile", "check"],
                cwd=tmp_dir,
                env=env,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                f"`python -m polyfile check` failed:\n{result.stdout}\n{result.stderr}",
            )
