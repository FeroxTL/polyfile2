"""Tests for django-axes integration."""

from datetime import timedelta

from axes.models import AccessAttempt
from django.test import TestCase, override_settings
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.accounts.models import ApiKey

AXES_TEST_SETTINGS = {
    "AXES_FAILURE_LIMIT": 3,
    "AXES_COOLOFF_TIME": timedelta(minutes=10),
    "AXES_LOCKOUT_PARAMETERS": [["ip_address", "username"]],
    "AXES_RESET_ON_SUCCESS": True,
}


@override_settings(**AXES_TEST_SETTINGS)
class AxesLoginTests(TestCase):
    """Brute-force protection for the web login form."""

    def setUp(self) -> None:
        super().setUp()
        self.user = UserFactory(username="axes-user")
        AccessAttempt.objects.all().delete()

    def tearDown(self) -> None:
        AccessAttempt.objects.all().delete()
        super().tearDown()

    def _login(self, username: str, password: str):
        return self.client.post(
            reverse("accounts-login"),
            {"username": username, "password": password},
        )

    def test_failed_login_attempts_are_recorded(self) -> None:
        self.assertEqual(AccessAttempt.objects.count(), 0)

        for _ in range(2):
            response = self._login("axes-user", "wrong-password")
            self.assertEqual(response.status_code, 200)

        attempt = AccessAttempt.objects.get()
        self.assertEqual(attempt.failures_since_start, 2)

    def test_login_is_locked_after_failure_limit(self) -> None:
        for _ in range(2):
            response = self._login("axes-user", "wrong-password")
            self.assertEqual(response.status_code, 200)

        # The third failure triggers lockout.
        response = self._login("axes-user", "wrong-password")
        self.assertEqual(response.status_code, 429)

        # Even valid credentials are rejected while locked out.
        response = self._login("axes-user", "pw")
        self.assertEqual(response.status_code, 429)
        self.assertIn("locked", response.content.decode().lower())

    def test_successful_login_resets_failed_attempts(self) -> None:
        for _ in range(2):
            self._login("axes-user", "wrong-password")
        self.assertEqual(AccessAttempt.objects.count(), 1)

        response = self._login("axes-user", "pw")
        self.assertIn(response.status_code, {200, 302})
        self.assertEqual(AccessAttempt.objects.count(), 0)


@override_settings(**AXES_TEST_SETTINGS)
class AxesApiKeyTests(TestCase):
    """Brute-force protection for API-key authentication."""

    def setUp(self) -> None:
        super().setUp()
        self.user = UserFactory(username="axes-api-user")
        self.api_key, self.token = ApiKey.create_for_user(self.user, "test-key")
        AccessAttempt.objects.all().delete()

    def tearDown(self) -> None:
        AccessAttempt.objects.all().delete()
        super().tearDown()

    def _api_request(self, token: str | None):
        headers = {}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = f"Bearer {token}"
        return self.client.get(reverse("fs_node") + "?path=/", **headers)

    def test_api_key_lockout_after_repeated_invalid_keys(self) -> None:
        for _ in range(2):
            response = self._api_request("pf_invalid_token")
            self.assertEqual(response.status_code, 401)

        # The third invalid attempt triggers lockout.
        response = self._api_request("pf_invalid_token")
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error_id"], "TooManyRequests")

    def test_valid_api_key_blocked_when_ip_locked(self) -> None:
        for _ in range(3):
            self._api_request("pf_invalid_token")

        response = self._api_request(self.token)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()["error_id"], "TooManyRequests")

    def test_api_key_empty_token_records_failure(self) -> None:
        self.assertEqual(AccessAttempt.objects.count(), 0)
        response = self._api_request("")
        self.assertEqual(response.status_code, 401)
        attempt = AccessAttempt.objects.get()
        self.assertEqual(attempt.failures_since_start, 1)
