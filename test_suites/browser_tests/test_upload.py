"""E2E tests for file upload."""

import tempfile
from pathlib import Path

import pytest

from test_suites.browser_tests.pages.dashboard import DashboardPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_upload_file_appears_in_list(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("hello from e2e")
        temp_path = Path(f.name)

    try:
        dashboard.upload_file(str(temp_path))
        names = dashboard.get_item_names()
        assert temp_path.name in names
    finally:
        temp_path.unlink(missing_ok=True)
