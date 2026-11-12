"""E2E tests for unauthorized access redirects."""

import re

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_files_redirects_anonymous_to_login(page, server_url):
    page.goto(f"{server_url}/files/")
    expect(page).to_have_url(re.compile(r"/accounts/login/"))


def test_dashboard_context_api_redirects_anonymous_to_login(page, server_url):
    page.goto(f"{server_url}/dashboard-context/")
    expect(page).to_have_url(re.compile(r"/accounts/login/"))
