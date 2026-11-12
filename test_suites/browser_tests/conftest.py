"""Shared fixtures for Polyfile browser end-to-end tests."""

import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from django.conf import settings as django_settings

# Set up a dedicated runtime data directory before Django imports settings.
_E2E_DATA_DIR = Path(tempfile.mkdtemp(prefix="polyfile-e2e-"))
os.environ["POLYFILE_DATA_DIR"] = str(_E2E_DATA_DIR)
os.environ.setdefault("SECRET_KEY", "django-insecure-e2e-tests")
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def _cleanup_e2e_data_dir() -> None:
    shutil.rmtree(_E2E_DATA_DIR, ignore_errors=True)


atexit.register(_cleanup_e2e_data_dir)


@pytest.fixture(scope="session", autouse=True)
def _build_frontend_assets() -> None:
    """Build production frontend assets once per test session.

    Set ``SKIP_FRONTEND_BUILD=1`` to reuse assets already present in
    ``polyfile/web_assets/``. This is useful for local iteration, but CI should
    always build from scratch.
    """
    if os.environ.get("SKIP_FRONTEND_BUILD", "0") == "1":
        return

    frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
    result = subprocess.run(
        ["cmd", "/c", "npm run build"],
        cwd=frontend_dir,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Frontend build failed:\n{result.stdout}\n{result.stderr}"
        )


@pytest.fixture(autouse=True)
def _configure_django_settings() -> None:
    """Ensure Django is pointed at the temporary E2E data directory."""
    django_settings.DATA_DIR = _E2E_DATA_DIR
    django_settings.STATIC_ROOT = _E2E_DATA_DIR / "static"
    django_settings.MEDIA_ROOT = _E2E_DATA_DIR / "media"
    django_settings.ARCHIVE_ROOT = _E2E_DATA_DIR / "archives"
    django_settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

    # Point the webpack loader at the freshly built production assets.
    project_root = Path(__file__).resolve().parent.parent.parent
    web_assets = project_root / "polyfile" / "web_assets"
    webpack_stats = project_root / "polyfile" / "webpack-stats.json"
    django_settings.WEBPACK_LOADER["DEFAULT"]["STATS_FILE"] = str(webpack_stats)
    django_settings.WEBPACK_ASSETS_DIR = str(web_assets)
    django_settings.STATICFILES_DIRS = (str(web_assets),)


@pytest.fixture
def e2e_data_dir() -> Path:
    """Return the temporary runtime data directory for the current session."""
    return _E2E_DATA_DIR


@pytest.fixture
def server_url(live_server) -> str:
    """Return the live Django server URL for Playwright."""
    return live_server.url


@pytest.fixture
def file_system_storage(e2e_data_dir: Path):
    """Create a local file system storage backend for E2E tests."""
    from polyfile.apps.storage.models import FsStorage
    from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
    from polyfile.contrib.backends.utils import get_storage_path

    storage_dir = e2e_data_dir / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage = FsStorage.objects.create(
        name="E2E Local Storage",
        backend=get_storage_path(FileSystemBackend),
        options={"location": str(storage_dir)},
    )
    yield storage


@pytest.fixture
def e2e_user(file_system_storage):
    """Create an authenticated user with a working file system storage."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(
        username="e2e-user",
        password="test-password",
        storage=file_system_storage,
    )
    yield user


@pytest.fixture
def authenticated_page(page, server_url: str, e2e_user):
    """Return a Playwright page authenticated as the E2E user."""
    from test_suites.browser_tests.pages.login import LoginPage

    login_page = LoginPage(page, server_url)
    login_page.login(e2e_user.username, "test-password")
    return page
