"""Base page object for Playwright E2E tests."""

from playwright.sync_api import Page


class PageObject:
    """Minimal base class for page objects."""

    def __init__(self, page: Page, base_url: str) -> None:
        self.page = page
        self.base_url = base_url.rstrip("/")
