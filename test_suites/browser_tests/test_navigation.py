"""E2E tests for dashboard navigation."""

import re

import pytest
from playwright.sync_api import expect

from test_suites.browser_tests.pages.dashboard import DashboardPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_root_directory_loads(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    expect(authenticated_page.locator("ol.breadcrumb")).to_contain_text("Files")
    breadcrumbs = dashboard.get_breadcrumbs()
    assert "Files" in breadcrumbs


def test_create_and_navigate_into_directory(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.create_directory("my-folder")
    dashboard.open_directory("my-folder")

    expect(authenticated_page).to_have_url(re.compile(r"/files/my-folder"))
    breadcrumbs = dashboard.get_breadcrumbs()
    assert "my-folder" in breadcrumbs
