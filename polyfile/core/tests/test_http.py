from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from polyfile.core.http import vary_on_accept, wants_html


class WantsHtmlTests(SimpleTestCase):
    def setUp(self) -> None:
        self.factory = RequestFactory()

    def test_browser_navigation_prefers_html(self) -> None:
        request = self.factory.get(
            "/",
            HTTP_ACCEPT="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        )

        self.assertTrue(wants_html(request))

    def test_json_accept_prefers_json(self) -> None:
        request = self.factory.get("/", HTTP_ACCEPT="application/json")

        self.assertFalse(wants_html(request))

    def test_wildcard_accept_defaults_to_json(self) -> None:
        request = self.factory.get("/", HTTP_ACCEPT="*/*")

        self.assertFalse(wants_html(request))

    def test_format_json_overrides_html_accept(self) -> None:
        request = self.factory.get(
            "/",
            {"format": "json"},
            HTTP_ACCEPT="text/html",
        )

        self.assertFalse(wants_html(request))

    def test_format_html_overrides_json_accept(self) -> None:
        request = self.factory.get(
            "/",
            {"format": "html"},
            HTTP_ACCEPT="application/json",
        )

        self.assertTrue(wants_html(request))

    def test_xhr_header_defaults_to_json(self) -> None:
        request = self.factory.get(
            "/",
            HTTP_ACCEPT="text/html",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertFalse(wants_html(request))


class VaryOnAcceptTests(SimpleTestCase):
    def test_appends_accept_without_dropping_existing_values(self) -> None:
        response = HttpResponse()
        response["Vary"] = "Cookie"

        result = vary_on_accept(response)

        self.assertIs(result, response)
        self.assertIn("Accept", response["Vary"])
        self.assertIn("Cookie", response["Vary"])

    def test_does_not_duplicate_accept(self) -> None:
        response = HttpResponse()
        vary_on_accept(response)

        vary_on_accept(response)

        self.assertEqual(response["Vary"], "Accept")
