"""E2E tests for public sharing."""

from urllib.parse import urlparse

import pytest

from test_suites.browser_tests.pages.dashboard import DashboardPage, PublicSharePage

pytestmark = [pytest.mark.django_db, pytest.mark.e2e]


def test_create_and_open_public_share(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.create_directory("shared-folder")
    dashboard.select_item("shared-folder")
    share_url = dashboard.create_share_link()
    assert share_url.startswith("http")

    # Open the public share in the same page to keep the test isolated.
    share_page = PublicSharePage(authenticated_page, server_url)
    share_page.navigate(share_url)
    assert share_page.get_current_name() == "shared-folder"


def test_public_share_navigates_into_subdirectory(authenticated_page, server_url):
    dashboard = DashboardPage(authenticated_page, server_url)
    dashboard.navigate()

    dashboard.create_directory("shared-folder")
    dashboard.open_directory("shared-folder")
    dashboard.create_directory("child-folder")

    dashboard.navigate()
    dashboard.select_item("shared-folder")
    share_url = dashboard.create_share_link()
    share_root_path = urlparse(share_url).path.rstrip("/")

    detail_requests: list[str] = []
    authenticated_page.on(
        "request",
        lambda request: detail_requests.append(request.url)
        if "/api/shares/detail/" in request.url
        else None,
    )

    share_page = PublicSharePage(authenticated_page, server_url)
    share_page.navigate(share_url)
    assert share_page.get_current_name() == "shared-folder"
    assert share_page.get_item_names() == ["child-folder"]
    assert len(detail_requests) == 1

    share_page.open_directory("child-folder")
    assert share_page.get_current_name() == "child-folder"
    assert urlparse(authenticated_page.url).path == f"{share_root_path}/child-folder"
    assert len(detail_requests) == 2

    share_page.open_breadcrumb("Files", expected_current_name="shared-folder")
    assert share_page.get_current_name() == "shared-folder"
    assert urlparse(authenticated_page.url).path == f"{share_root_path}/"
    assert len(detail_requests) == 3

