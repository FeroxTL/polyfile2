"""E2E tests for dashboard breadcrumb navigation."""

import re

import pytest
from playwright.sync_api import expect

from test_suites.browser_tests.pages.dashboard import DashboardPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_breadcrumb_files_returns_to_root(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.create_directory("nested")
    dashboard.open_directory("nested")
    expect(authenticated_page).to_have_url(re.compile(r"/files/nested"))

    dashboard.open_breadcrumb("Files")
    expect(authenticated_page).to_have_url(re.compile(r"/files/?$"))
