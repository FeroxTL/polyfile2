"""E2E tests for authentication flows."""

import re

import pytest
from playwright.sync_api import expect

from test_suites.browser_tests.pages.dashboard import DashboardPage
from test_suites.browser_tests.pages.login import LoginPage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_login_redirects_to_dashboard(page, server_url, e2e_user):
    login_page = LoginPage(page, server_url)
    login_page.login(e2e_user.username, "test-password")

    dashboard = DashboardPage(page, server_url)
    dashboard.wait_for_loaded()
    expect(page).to_have_url(re.compile(r"/files/"))
