"""Page object for the Django login page."""

from playwright.sync_api import expect

from test_suites.browser_tests.pages.base import PageObject


class LoginPage(PageObject):
    """Interact with the Django login form."""

    def navigate(self) -> None:
        self.page.goto(f"{self.base_url}/accounts/login/")

    def login(self, username: str, password: str) -> None:
        self.navigate()
        self.page.fill('input[name="username"]', username)
        self.page.fill('input[name="password"]', password)
        self.page.click('button[type="submit"]')
        self.page.wait_for_url("**/files/**")
        expect(self.page.locator("ol.breadcrumb")).to_contain_text("Files")
