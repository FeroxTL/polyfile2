import json
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.accounts.models import ApiKey
from polyfile.apps.storage.factories import FsNodeDirectoryFactory
from polyfile.apps.storage.models import TempUpload


class ApiKeyTestBase(TestCase):
    """Shared fixtures for API-key tests."""

    def setUp(self) -> None:
        super().setUp()
        self.user = UserFactory(username="api-key-user")
        self.storage = self.user.storage
        self.root = FsNodeDirectoryFactory(
            name="root",
            owner=self.user,
            storage=self.storage,
        )
        self.api_key, self.token = ApiKey.create_for_user(
            self.user,
            "test-key",
        )

    def auth_headers(self, token: str | None = None) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {token or self.token}"}


class ApiKeyModelTests(ApiKeyTestBase):
    def test_token_is_not_stored_in_plaintext(self) -> None:
        stored = ApiKey.objects.get(pk=self.api_key.pk)

        self.assertNotEqual(stored.key_hash, self.token)
        self.assertNotIn(self.token, stored.key_hash)
        self.assertEqual(stored.key_hash, ApiKey.hash_token(self.token))
        self.assertTrue(self.token.startswith(f"pf_{stored.prefix}_"))

    def test_authenticate_returns_key_for_valid_token(self) -> None:
        self.assertEqual(ApiKey.authenticate(self.token), self.api_key)

    def test_authenticate_rejects_token_with_wrong_secret(self) -> None:
        prefix, _secret = ApiKey.parse_token(self.token)
        self.assertIsNone(ApiKey.authenticate(f"pf_{prefix}_wrong-secret"))

    def test_authenticate_rejects_malformed_token(self) -> None:
        self.assertIsNone(ApiKey.parse_token("not-a-token"))
        self.assertIsNone(ApiKey.authenticate("not-a-token"))

    def test_revoked_key_is_not_active(self) -> None:
        self.api_key.revoke()

        self.api_key.refresh_from_db()
        self.assertFalse(self.api_key.is_active)
        self.assertIsNone(ApiKey.authenticate(self.token))

    def test_expired_key_is_not_active(self) -> None:
        self.api_key.expires_at = now() - timedelta(seconds=1)
        self.api_key.save(update_fields=("expires_at",))

        self.assertFalse(self.api_key.is_active)
        self.assertIsNone(ApiKey.authenticate(self.token))

    def test_key_of_inactive_user_is_rejected(self) -> None:
        self.user.is_active = False
        self.user.save(update_fields=("is_active",))

        self.assertIsNone(ApiKey.authenticate(self.token))


class ApiKeyAuthenticationTests(ApiKeyTestBase):
    def test_bearer_token_authenticates_api_request(self) -> None:
        response = self.client.get(reverse("fs_node") + "?path=/", **self.auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [child["name"] for child in response.json()["children"]],
            ["root"],
        )

    def test_x_api_key_header_authenticates_api_request(self) -> None:
        response = self.client.get(
            reverse("fs_node") + "?path=/",
            HTTP_X_API_KEY=self.token,
        )

        self.assertEqual(response.status_code, 200)

    def test_invalid_token_returns_401(self) -> None:
        response = self.client.get(
            reverse("fs_node") + "?path=/",
            **self.auth_headers("pf_invalid"),
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error_id"], "Unauthorized")
        self.assertEqual(response["WWW-Authenticate"], "Bearer")

    def test_empty_bearer_token_returns_401(self) -> None:
        response = self.client.get(
            reverse("fs_node") + "?path=/",
            HTTP_AUTHORIZATION="Bearer ",
        )

        self.assertEqual(response.status_code, 401)

    def test_revoked_key_returns_401(self) -> None:
        self.api_key.revoke()

        response = self.client.get(reverse("fs_node") + "?path=/", **self.auth_headers())

        self.assertEqual(response.status_code, 401)

    def test_expired_key_returns_401(self) -> None:
        self.api_key.expires_at = now() - timedelta(seconds=1)
        self.api_key.save(update_fields=("expires_at",))

        response = self.client.get(reverse("fs_node") + "?path=/", **self.auth_headers())

        self.assertEqual(response.status_code, 401)

    def test_session_authentication_still_works(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("fs_node") + "?path=/")

        self.assertEqual(response.status_code, 200)

    def test_key_cannot_access_another_users_nodes(self) -> None:
        other_user = UserFactory(username="api-key-other-user")
        FsNodeDirectoryFactory(
            name="other-root",
            owner=other_user,
            storage=other_user.storage,
        )

        response = self.client.get(reverse("fs_node") + "?path=/", **self.auth_headers())

        self.assertEqual(response.status_code, 200)
        names = [child["name"] for child in response.json()["children"]]
        self.assertIn("root", names)
        self.assertNotIn("other-root", names)

    def test_key_can_access_own_node_detail(self) -> None:
        response = self.client.get(
            reverse("fs_node") + "?path=/",
            **self.auth_headers(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current"]["name"], "")

    def test_last_used_at_is_updated_when_stale(self) -> None:
        stale = now() - timedelta(minutes=5)
        ApiKey.objects.filter(pk=self.api_key.pk).update(last_used_at=stale)

        response = self.client.get(reverse("fs_node") + "?path=/", **self.auth_headers())

        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertGreater(self.api_key.last_used_at, stale)

    def test_last_used_at_is_not_updated_within_throttle_window(self) -> None:
        recent = now() - timedelta(seconds=30)
        ApiKey.objects.filter(pk=self.api_key.pk).update(last_used_at=recent)

        response = self.client.get(reverse("fs_node") + "?path=/", **self.auth_headers())

        self.assertEqual(response.status_code, 200)
        self.api_key.refresh_from_db()
        self.assertEqual(self.api_key.last_used_at, recent)


class ApiKeyUploadTests(ApiKeyTestBase):
    def test_touch_and_upload_work_without_session(self) -> None:
        touch_response = self.client.post(
            reverse("fs_node_touch"),
            data=json.dumps({"parent_id": None, "name": "upload.txt"}),
            content_type="application/json",
            **self.auth_headers(),
        )

        self.assertEqual(touch_response.status_code, 200, touch_response.json())
        upload_url = touch_response.json()["upload_url"]
        upload_response = self.client.post(
            upload_url,
            data=b"hello",
            content_type="application/octet-stream",
        )

        self.assertEqual(upload_response.status_code, 200)
        self.assertEqual(
            TempUpload.objects.get(
                fs_node__name="upload.txt",
            ).status,
            TempUpload.Status.COMPLETE,
        )


class CreateApiKeyCommandTests(ApiKeyTestBase):
    def test_command_prints_usable_token(self) -> None:
        stdout = StringIO()

        call_command(
            "create_api_key",
            username=self.user.username,
            name="cli-key",
            stdout=stdout,
        )

        token = stdout.getvalue().strip().splitlines()[-1]
        self.assertIsNotNone(ApiKey.authenticate(token))

    def test_command_json_output(self) -> None:
        stdout = StringIO()

        call_command(
            "create_api_key",
            username=self.user.username,
            name="json-key",
            json=True,
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["name"], "json-key")
        self.assertIsNotNone(ApiKey.authenticate(payload["token"]))

    def test_command_sets_expiry(self) -> None:
        stdout = StringIO()

        call_command(
            "create_api_key",
            username=self.user.username,
            name="expiring-key",
            expires_in="1h",
            stdout=stdout,
        )

        api_key = ApiKey.objects.get(name="expiring-key")
        self.assertIsNotNone(api_key.expires_at)
        self.assertGreater(api_key.expires_at, now())

    def test_command_rejects_unknown_user(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "create_api_key",
                username="missing-user",
                name="missing",
                stdout=StringIO(),
            )
