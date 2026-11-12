"""E2E tests for the public shares dashboard."""

import pytest

from test_suites.browser_tests.pages.dashboard import DashboardPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_created_share_appears_in_shares_list(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.create_directory("shared-for-list")
    dashboard.select_item("shared-for-list")
    share_url = dashboard.create_share_link()
    assert share_url.startswith("http")

    dashboard.navigate_to_shares()
    names = dashboard.get_share_names()
    assert "shared-for-list" in names
