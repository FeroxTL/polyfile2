"""E2E tests for node deletion."""

import pytest
from playwright.sync_api import expect

from test_suites.browser_tests.pages.dashboard import DashboardPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_delete_directory_removes_it_from_list(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.create_directory("to-delete")
    names = dashboard.get_item_names()
    assert "to-delete" in names

    dashboard.select_item("to-delete")
    dashboard.delete_selected()

    expect(authenticated_page.locator("li:has-text('to-delete')")).to_have_count(0)
    names = dashboard.get_item_names()
    assert "to-delete" not in names
