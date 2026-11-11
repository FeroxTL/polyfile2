import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class RuntimeDataDirTests(SimpleTestCase):
    def test_settings_use_polyfile_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env["POLYFILE_DATA_DIR"] = tmp_dir
            env["DJANGO_SETTINGS_MODULE"] = "polyfile.core.settings"
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
            )
            env.pop("DATABASE_URL", None)

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "from django.conf import settings; "
                        "print(json.dumps({"
                        "'data_dir': str(settings.DATA_DIR), "
                        "'database': settings.DATABASES['default']['NAME'], "
                        "'static_root': str(settings.STATIC_ROOT), "
                        "'media_root': str(settings.MEDIA_ROOT), "
                        "'archive_root': str(settings.ARCHIVE_ROOT), "
                        "'archive_max_size': settings.DIRECTORY_ARCHIVE_MAX_SIZE, "
                        "}))"
                    ),
                ],
                cwd=tmp_dir,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            paths = json.loads(result.stdout)
            expected = Path(tmp_dir).resolve()

            self.assertEqual(Path(paths["data_dir"]), expected)
            self.assertEqual(Path(paths["database"]), expected / "db.sqlite3")
            self.assertEqual(Path(paths["static_root"]), expected / "static")
            self.assertEqual(Path(paths["media_root"]), expected / "media")
            self.assertEqual(Path(paths["archive_root"]), expected / "archives")
            self.assertEqual(paths["archive_max_size"], 10 * 1024 ** 3)
            self.assertTrue((expected / "archives").is_dir())

    def test_settings_default_to_local_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = os.environ.copy()
            env.pop("POLYFILE_DATA_DIR", None)
            env.pop("DATABASE_URL", None)
            env["DJANGO_SETTINGS_MODULE"] = "polyfile.core.settings"
            env["PYTHONPATH"] = os.pathsep.join(
                filter(None, [str(PROJECT_ROOT), env.get("PYTHONPATH", "")])
            )

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import json; "
                        "from django.conf import settings; "
                        "print(json.dumps({"
                        "'data_dir': str(settings.DATA_DIR), "
                        "'database': settings.DATABASES['default']['NAME'], "
                        "'static_root': str(settings.STATIC_ROOT), "
                        "'media_root': str(settings.MEDIA_ROOT), "
                        "'archive_root': str(settings.ARCHIVE_ROOT), "
                        "'archive_max_size': settings.DIRECTORY_ARCHIVE_MAX_SIZE, "
                        "}))"
                    ),
                ],
                cwd=tmp_dir,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            paths = json.loads(result.stdout)
            expected = Path(tmp_dir).resolve() / "local"

            self.assertEqual(Path(paths["data_dir"]), expected)
            self.assertEqual(Path(paths["database"]), expected / "db.sqlite3")
            self.assertEqual(Path(paths["static_root"]), expected / "static")
            self.assertEqual(Path(paths["media_root"]), expected / "media")
            self.assertEqual(Path(paths["archive_root"]), expected / "archives")
            self.assertEqual(paths["archive_max_size"], 10 * 1024 ** 3)
            self.assertTrue(expected.is_dir())
            self.assertTrue((expected / "archives").is_dir())
