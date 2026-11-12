"""Page object for the file manager dashboard SPA."""

import re

from playwright.sync_api import expect

from test_suites.browser_tests.pages.base import PageObject


class DashboardPage(PageObject):
    """Interact with the main file dashboard."""

    def navigate(self) -> "DashboardPage":
        self.page.goto(f"{self.base_url}/files/")
        self.wait_for_loaded()
        return self

    def wait_for_loaded(self) -> None:
        self.page.wait_for_selector("ol.breadcrumb", state="visible")

    def create_directory(self, name: str) -> None:
        self.page.click("button:has-text('Create')")
        modal = self.page.locator(".modal-content")
        expect(modal).to_be_visible()
        modal.locator("input").fill(name)
        modal.locator("button:has-text('Create')").last.click()
        self.page.wait_for_selector(f"li:has-text('{name}')", state="visible")

    def upload_file(self, file_path: str) -> None:
        file_input = self.page.locator('input[type="file"]').first
        file_input.set_input_files(file_path)
        # Wait until the upload flow finishes and the new file row appears.
        self.page.wait_for_selector(
            "ul.list-group.user-select-none li",
            state="visible",
        )

    def open_directory(self, name: str) -> None:
        self.page.dblclick(f"li:has-text('{name}'):has(.fa-folder)")
        self.page.wait_for_url(re.compile(rf"/files/{name}"))
        self.wait_for_loaded()

    def select_item(self, name: str) -> None:
        self.page.click(f"li:has-text('{name}'):has(.fa-folder), li:has-text('{name}'):has(.fa-file)")

    def delete_selected(self) -> None:
        self.page.click("a:has-text('Remove')")
        modal = self.page.locator(".modal-content")
        expect(modal).to_be_visible()
        modal.locator("button[type='submit']").click()
        self.page.wait_for_load_state("networkidle")

    def open_share_modal(self) -> None:
        self.page.click("a:has-text('Share')")
        expect(self.page.locator(".modal-content")).to_be_visible()

    def create_share_link(self) -> str:
        self.open_share_modal()
        modal = self.page.locator(".modal-content")
        modal.locator("button:has-text('Create Share Link')").click()
        link_input = modal.locator("input[type='text']")
        link_input.wait_for(state="visible")
        return link_input.input_value()

    def get_item_names(self) -> list[str]:
        return self.page.locator("ul.list-group li span.flex-grow-1").all_inner_texts()

    def get_breadcrumbs(self) -> list[str]:
        return self.page.locator("ol.breadcrumb li").all_inner_texts()

    def open_breadcrumb(self, name: str) -> None:
        self.page.click(f"ol.breadcrumb a:has-text('{name}')")
        self.page.wait_for_url(re.compile(r"/files/?$"))

    def navigate_to_shares(self) -> None:
        self.page.goto(f"{self.base_url}/shares")
        self.page.wait_for_selector("h4:has-text('Public links')", state="visible")

    def get_share_names(self) -> list[str]:
        return self.page.locator("ul.list-group li span.flex-grow-1").all_inner_texts()

    def get_create_directory_validation_error(self) -> str | None:
        modal = self.page.locator(".modal-content")
        feedback = modal.locator(".invalid-feedback")
        if feedback.count() == 0:
            return None
        return feedback.first.inner_text()


class PublicSharePage(PageObject):
    """Interact with a public share page."""

    def navigate(self, url: str) -> None:
        self.page.goto(url)
        self.page.wait_for_selector("ol.breadcrumb", state="visible")

    def open_directory(self, name: str) -> None:
        self.page.dblclick(f"li:has-text('{name}'):has(.fa-folder)")
        self.page.wait_for_function(
            "name => document.querySelector('h1.h2')?.textContent.trim() === name",
            arg=name,
        )

    def open_breadcrumb(self, name: str, expected_current_name: str) -> None:
        self.page.click(f"ol.breadcrumb a:has-text('{name}')")
        self.page.wait_for_function(
            "name => document.querySelector('h1.h2')?.textContent.trim() === name",
            arg=expected_current_name,
        )

    def get_item_names(self) -> list[str]:
        return self.page.locator("ul.list-group li span.flex-grow-1").all_inner_texts()

    def get_current_name(self) -> str:
        return self.page.locator("h1.h2").inner_text()

    def has_error(self) -> bool:
        return self.page.locator(".card.bg-warning").count() > 0
