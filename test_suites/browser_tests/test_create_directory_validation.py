"""E2E tests for directory creation validation."""

import pytest
from playwright.sync_api import expect

from test_suites.browser_tests.pages.dashboard import DashboardPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_create_directory_with_slash_shows_validation_error(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.page.click("button:has-text('Create')")
    modal = dashboard.page.locator(".modal-content")
    expect(modal).to_be_visible()
    modal.locator("input").fill("invalid/name")

    feedback = modal.locator(".invalid-feedback")
    expect(feedback).to_be_visible()
    error = feedback.inner_text()
    assert "/" in error
