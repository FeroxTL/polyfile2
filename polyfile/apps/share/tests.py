import json
import tempfile
import uuid
from datetime import timedelta
from unittest import mock
from urllib.parse import urlencode

from django.core.files.base import ContentFile
from django.http.response import StreamingHttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.share.models import SharedNode, ShareDownload
from polyfile.apps.share.services import create_public_share
from polyfile.apps.share.utils import (
    generate_download_token,
    share_download_url,
    time_to_offset,
    validate_download_token,
)
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path
from polyfile.core.exceptions import Unauthorized


class ShareBaseTest(TestCase):
    """Shared fixtures for share tests."""

    def setUp(self):
        """Set up a real local-disk storage, users and a small tree."""
        super().setUp()
        self.temp_dir = self.enterContext(tempfile.TemporaryDirectory())

        self.owner = UserFactory(username="share_owner")

        self.storage = StorageFactory(
            backend=get_storage_path(FileSystemBackend),
            options={
                "location": str(self.temp_dir),
                "upload_to": "",
            },
        )

        self.root_dir = FsNodeDirectoryFactory(
            name="root_dir",
            owner=self.owner,
            storage=self.storage,
        )
        self.child_file = FsNodeFileFactory(
            name="notes.txt",
            owner=self.owner,
            size=5,
            storage=self.storage,
            parent=self.root_dir,
        )
        self.child_file.file.save("notes.txt", ContentFile(b"hello"), save=True)
        self.child_dir = FsNodeDirectoryFactory(
            name="nested",
            owner=self.owner,
            storage=self.storage,
            parent=self.root_dir,
        )


class ShareCreationTests(ShareBaseTest):
    def setUp(self):
        """Test setUp."""
        super().setUp()
        self.other_user = UserFactory(username="other_user")

    @staticmethod
    def _create_url(path: str = "/root_dir") -> str:
        return reverse("share-create", kwargs={"path": path})

    def test_create_share_success(self):
        """Verify that user_a can create a share for root_dir."""
        share = create_public_share(self.owner, self.root_dir)

        self.assertIsInstance(share, SharedNode)
        self.assertEqual(share.owner, self.owner)
        self.assertEqual(share.root_fs_node, self.root_dir)

    def test_create_share_unauthorized(self):
        """Verify that other_user cannot create a share for root_dir."""
        self.client.force_login(self.other_user)
        response = self.client.post(self._create_url())
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                "error_id": "FieldValidationError",
                "description": "Error validating fields.",
                "detail": {"path": ["FsNode not found."]},
            },
        )

    def test_create_share_not_found(self):
        """Verify that sharing a non-existent path returns a validation error."""
        self.client.force_login(self.owner)
        response = self.client.post(self._create_url("/does-not-exist"))
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                "error_id": "FieldValidationError",
                "description": "Error validating fields.",
                "detail": {"path": ["FsNode not found."]},
            },
        )

    def test_create_share_for_root_is_rejected(self):
        """The user root is not a real FsNode and can not be shared."""
        self.client.force_login(self.owner)
        response = self.client.post(self._create_url("/"))
        self.assertEqual(response.status_code, 400)
        self.assertDictEqual(
            response.json(),
            {
                "error_id": "FieldValidationError",
                "description": "Error validating fields.",
                "detail": {"path": ["FsNode not found."]},
            },
        )

    def test_reactivate_revoked_share(self):
        """Test that sharing again reactivates and resets the existing share."""
        self.client.force_login(self.owner)

        # Create and revoke/expire share
        share = create_public_share(self.owner, self.root_dir)
        old_token = share.token
        share.revoked_at = now()
        share.expires_at = now() - timedelta(days=1)
        share.save()

        # Create share again for same node
        response = self.client.post(self._create_url())
        self.assertEqual(response.status_code, 200)
        share.refresh_from_db()
        self.assertNotEqual(share.token, old_token)
        self.assertDictEqual(
            response.json(),
            {
                "id": str(share.token),
                "url": mock.ANY,
                "status": "active",
                "expires_at": None,
                "revoked_at": None,
                "root_fs_node": {
                    "id": str(share.root_fs_node.id),
                    "name": "root_dir",
                    "type": "directory",
                    "path": None,
                },
                "created_at": share.created_at.isoformat(),
            }, response.json()
        )
        self.assertIn(f"/s/{share.token}/", response.json()["url"])

        # It should be the same share object
        self.assertEqual(SharedNode.objects.count(), 1)
        self.assertIsNone(share.revoked_at)
        self.assertIsNone(share.expires_at)

    def test_create_share_keeps_active_token(self):
        """Repeated create requests for an active share return the same link."""
        self.client.force_login(self.owner)

        first = self.client.post(self._create_url())
        second = self.client.post(self._create_url())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(SharedNode.objects.count(), 1)

    def test_create_share_view(self):
        """Test create share."""
        self.client.force_login(self.owner)
        response = self.client.post(self._create_url())

        self.assertEqual(response.status_code, 200)
        share = SharedNode.objects.get(root_fs_node=self.root_dir)
        self.assertDictEqual(
            response.json(),
            {
                "id": str(share.token),
                "url": mock.ANY,
                "status": "active",
                "expires_at": None,
                "revoked_at": None,
                "root_fs_node": {
                    "id": str(share.root_fs_node.id),
                    "name": "root_dir",
                    "type": "directory",
                    "path": "/root_dir",
                },
                "created_at": share.created_at.isoformat(),
            },
        )
        self.assertIn(f"/s/{share.token}/", response.json()["url"])


class ShareRevocationTests(ShareBaseTest):
    """Revocation must be owner-scoped, soft, and invalidate the public URL."""

    def setUp(self):
        """Create an active share and a second user."""
        super().setUp()
        self.other_user = UserFactory(username="share_other_user")
        self.share = create_public_share(self.owner, self.root_dir)

    @staticmethod
    def _revoke_url(share_token: str | uuid.UUID) -> str:
        return reverse("share-api-revoke", kwargs={"share_token": str(share_token)})

    def test_revoke_share_is_a_soft_delete(self):
        """A successful revoke keeps the row but marks it as revoked."""
        self.client.force_login(self.owner)

        response = self.client.post(self._revoke_url(self.share.token))

        self.assertEqual(response.status_code, 204)
        self.share.refresh_from_db()
        self.assertIsNotNone(self.share.revoked_at)
        self.assertFalse(self.share.is_active)
        self.assertEqual(SharedNode.objects.count(), 1)

    def test_revoke_share_is_idempotent(self):
        """Revoking an already revoked share keeps the original timestamp."""
        self.client.force_login(self.owner)

        self.assertEqual(self.client.post(self._revoke_url(self.share.token)).status_code, 204)
        self.share.refresh_from_db()
        revoked_at = self.share.revoked_at

        self.assertEqual(self.client.post(self._revoke_url(self.share.token)).status_code, 204)
        self.share.refresh_from_db()
        self.assertEqual(self.share.revoked_at, revoked_at)

    def test_revoke_share_of_another_user_is_not_found(self):
        """A user cannot revoke somebody else's share by guessing its token."""
        self.client.force_login(self.other_user)

        response = self.client.post(self._revoke_url(self.share.token))

        self.assertEqual(response.status_code, 404)
        self.share.refresh_from_db()
        self.assertIsNone(self.share.revoked_at)

    def test_revoked_share_url_stops_working(self):
        """The old public URL must return 404 immediately after revocation."""
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self._revoke_url(self.share.token)).status_code, 204)
        self.client.logout()

        response = self.client.get(reverse(
            "share-api-detail-path",
            kwargs={"share_token": str(self.share.token), "path": "/"},
        ))

        self.assertEqual(response.status_code, 404)

    def test_recreate_after_revoke_rotates_token(self):
        """Sharing again after revoke returns a new link and no longer revoked share."""
        self.client.force_login(self.owner)
        old_token = self.share.token
        self.assertEqual(self.client.post(self._revoke_url(old_token)).status_code, 204)

        response = self.client.post(reverse(
            "share-create",
            kwargs={"path": f"/{self.root_dir.name}"},
        ))

        self.assertEqual(response.status_code, 200)
        self.share.refresh_from_db()
        self.assertNotEqual(self.share.token, old_token)
        self.assertEqual(response.json()["id"], str(self.share.token))
        self.assertIsNone(self.share.revoked_at)
        self.assertTrue(self.share.is_active)


class FsNodeListShareInfoTests(ShareBaseTest):
    """The dashboard file list must expose public share info."""

    def _list(self, path: str = "/") -> dict:
        self.client.force_login(self.owner)
        response = self.client.get(reverse("fs_node"), {"path": path})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_share_info_is_returned_for_a_child(self):
        """An active share of a child node is exposed with its id and URL."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)

        data = self._list("/")
        children = {item["name"]: item for item in data["children"]}
        share_info = children[self.root_dir.name]["share"]

        self.assertIsNone(data["current"]["share"])
        self.assertEqual(share_info["id"], str(share.token))
        self.assertIn(f"/s/{share.token}/", share_info["url"])
        self.assertTrue(share_info["url"].startswith("http"))

    def test_share_info_is_returned_for_current_node(self):
        """An active share of the current node is exposed too."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)

        data = self._list(f"/{self.root_dir.name}")

        self.assertEqual(data["current"]["share"]["id"], str(share.token))
        self.assertIn(f"/s/{share.token}/", data["current"]["share"]["url"])


class ShareActiveManagerTests(TestCase):
    """
    Pin the expiry semantics of ``SharedNode.active`` (defect D6).

    The manager and the ``is_active`` property must agree. Today the manager's filter is
    ``expires_at__lte=now``, which *excludes* every share that has not expired yet, so a
    valid non-expiring-in-the-future share is invisible to ``.active.get()`` and the whole
    share API answers 404.
    """

    def test_share_without_expiry_is_active(self):
        """A share with no ``expires_at`` is active and visible through the manager."""
        share = SharedNodeFactory(expires_at=None)

        self.assertEqual(SharedNode.active.get(token=share.token), share)
        self.assertTrue(share.is_active)
        self.assertIsNone(share.expires_at)

    def test_share_with_future_expiry_is_active(self):
        """A share with a future ``expires_at`` is active and visible through the manager."""
        share = SharedNodeFactory(expires_at=now() + timedelta(days=1))

        self.assertTrue(share.is_active)
        self.assertEqual(SharedNode.active.get(token=share.token), share)
        self.assertTrue(share.expires_at > now())

    def test_share_expired_in_the_past_is_inactive(self):
        """A share whose ``expires_at`` has passed is not active."""
        share = SharedNodeFactory(expires_at=now() - timedelta(days=1))

        self.assertFalse(share.is_active)
        self.assertTrue(share.expires_at < now())
        with self.assertRaises(SharedNode.DoesNotExist):
            SharedNode.active.get(token=share.token)

    def test_revoked_share(self):
        """A revoked share is not active even when it has no expiry."""
        share = SharedNodeFactory(revoked_at=now())

        self.assertFalse(share.is_active)
        with self.assertRaises(SharedNode.DoesNotExist):
            SharedNode.active.get(token=share.token)

        # Clearing ``revoked_at`` makes the share visible to the manager again.
        share.revoked_at = None
        share.save(update_fields=("revoked_at",))

        self.assertTrue(share.is_active)
        self.assertEqual(SharedNode.active.get(token=share.token), share)


class ShareDetailApiTests(ShareBaseTest):
    """
    Pin the contract of ``GET /api/shares/details/<share_token>/<path>``.

    This is the endpoint the public SPA consumes. It must work for an anonymous visitor
    (D2), return a serializable payload (D3), walk the tree correctly (D4, D5), speak the
    same ``type`` vocabulary as the storage API (D7), and hand out signed download links
    (D10).
    """
    maxDiff = None

    @staticmethod
    def _api_url(share_token: str | uuid.UUID, path: str = "/") -> str:
        return reverse("share-api-detail-path", kwargs={"share_token": str(share_token), "path": path})

    def test_share_not_found(self) -> None:
        """Check invalid share link."""
        self.client.logout()

        random_uuid = uuid.uuid4()
        response = self.client.get(self._api_url(random_uuid, "/"))
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                "description": "Not found.",
                "detail": f"Share with token {random_uuid} does not exist.",
                "error_id": "NotFound",
            },
        )

    def test_inactive_share(self) -> None:
        """Check invalid share link."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir, revoked_at=now())
        self.client.logout()
        response = self.client.get(self._api_url(share.token, "/"))
        self.assertEqual(response.status_code, 404)
        self.assertDictEqual(
            response.json(),
            {
                "description": "Not found.",
                "detail": f"Share with token {share.token} does not exist.",
                "error_id": "NotFound",
            },
        )

    def test_download_inactive_file_share(self) -> None:
        """Check download link in invalid share."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir, revoked_at=now())
        self.client.login()
        file_response = self.client.get(share_download_url(share.token, self.child_file.id))
        self.assertEqual(file_response.status_code, 404)
        # TODO check response.json()

    def test_download_invalid_url_sign(self) -> None:
        """Check download link sign."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)
        self.client.login()
        with mock.patch("polyfile.apps.share.utils.generate_download_token", return_value="foo"):
            file_response = self.client.get(share_download_url(share.token, self.child_file.id))
        self.assertEqual(file_response.status_code, 404)
        # TODO check response.json()

    def test_download_inactive_directory_share(self) -> None:
        """
        Check download directory in share.

        This function is not implemented yet, so this tests only 404 template.
        """
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)
        self.client.login()
        file_response = self.client.get(share_download_url(share.token, self.root_dir.id))
        self.assertEqual(file_response.status_code, 404)
        # TODO check response.json()

    def test_root_details_are_publicly_accessible(self) -> None:
        """Check that anonymous visitor gets the root node and its children in payload."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)
        self.client.logout()
        response = self.client.get(self._api_url(share.token, "/"))
        self.assertEqual(response.status_code, 200)

        self.assertDictEqual(
            response.json(),
            {
                "current": {
                    "name": self.root_dir.name,
                    "type": FsNode.TypeChoices.DIRECTORY.value,
                    "created_at": self.root_dir.created_at.isoformat(),
                    "modified_at": self.root_dir.modified_at.isoformat(),
                    "size": 0,
                    "mime_type": "",
                    "md5": "",
                    "file": "",
                    "download_url": "",
                    "path": "/",
                },
                "children": [
                    {
                        "created_at": self.child_dir.created_at.isoformat(),
                        "download_url": "",
                        "file": "",
                        "md5": "",
                        "mime_type": "",
                        "modified_at": self.child_dir.modified_at.isoformat(),
                        "name": self.child_dir.name,
                        "size": 0,
                        "type": FsNode.TypeChoices.DIRECTORY.value,
                    },
                    {
                        "created_at": self.child_file.created_at.isoformat(),
                        "download_url": mock.ANY,
                        "file": "notes.txt",
                        "md5": self.child_file.md5,
                        "mime_type": self.child_file.mime_type,
                        "modified_at": self.child_file.modified_at.isoformat(),
                        "name": self.child_file.name,
                        "size": self.child_file.size,
                        "type": FsNode.TypeChoices.FILE.value,
                    },
                ],
            },
        )

        file_response = self.client.get(response.json()["children"][1]["download_url"])
        self.assertIsInstance(file_response, StreamingHttpResponse)
        self.assertEqual(file_response.status_code, 200)
        self.assertEqual(b''.join(file_response.streaming_content), b"hello")

    def test_child_details_are_publicly_accessible(self) -> None:
        """Check that anonymous visitor gets the child node and its children in payload."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)
        nested_file = FsNodeFileFactory(
            owner=self.owner,
            storage=self.storage,
            parent=self.child_dir,
        )
        self.client.logout()
        response = self.client.get(self._api_url(share.token, f"/{self.child_dir.name}"))
        self.assertEqual(response.status_code, 200)

        self.assertDictEqual(
            response.json(),
            {
                "current": {
                    "name": self.child_dir.name,
                    "type": FsNode.TypeChoices.DIRECTORY.value,
                    "created_at": self.child_dir.created_at.isoformat(),
                    "modified_at": self.child_dir.modified_at.isoformat(),
                    "size": 0,
                    "mime_type": "",
                    "md5": "",
                    "file": "",
                    "download_url": "",
                    "path": f"/{self.child_dir.name}",
                },
                "children": [
                    {
                        "created_at": nested_file.created_at.isoformat(),
                        "download_url": mock.ANY,
                        "file": nested_file.file,
                        "md5": nested_file.md5,
                        "mime_type": nested_file.mime_type,
                        "modified_at": nested_file.modified_at.isoformat(),
                        "name": nested_file.name,
                        "size": nested_file.size,
                        "type": FsNode.TypeChoices.FILE.value,
                    },
                ],
            },
        )

    def test_child_file_details_are_publicly_accessible(self) -> None:
        """Check that anonymous visitor gets the child node of type "file" and no children in payload."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)
        self.client.logout()
        response = self.client.get(self._api_url(share.token, f"/{self.child_file.name}"))

        self.assertEqual(response.status_code, 200)
        self.assertDictEqual(
            response.json(),
            {
                "current": {
                    "name": self.child_file.name,
                    "type": FsNode.TypeChoices.FILE.value,
                    "created_at": self.child_file.created_at.isoformat(),
                    "modified_at": self.child_file.modified_at.isoformat(),
                    "size": self.child_file.size,
                    "mime_type": self.child_file.mime_type,
                    "md5": self.child_file.md5,
                    "file": self.child_file.file,
                    "download_url": mock.ANY,
                    "path": f"/{self.child_file.name}",
                },
                "children": [],
            },
        )

        file_response = self.client.get(response.json()["current"]["download_url"])
        self.assertEqual(file_response.status_code, 200)
        self.assertIsInstance(file_response, StreamingHttpResponse)
        self.assertEqual(b''.join(file_response.streaming_content), b"hello")
        file_response.close()


class DownloadTokenValidationTests(TestCase):
    def setUp(self):
        super().setUp()
        self.share_token = str(uuid.uuid4())
        self.fs_node_pk = str(uuid.uuid4())

    def test_valid_token_not_expired(self):
        """Test that a valid, non-expired token returns True."""
        expiration_time = now() + timedelta(hours=1)
        signature = generate_download_token(self.share_token, self.fs_node_pk, expiration_time)
        time_offset = time_to_offset(expiration_time)

        self.assertTrue(validate_download_token(self.share_token, self.fs_node_pk, time_offset, signature))

    def test_valid_token_expired(self):
        """Test that a valid, expired token returns False."""
        expiration_time = now() - timedelta(hours=1)
        signature = generate_download_token(self.share_token, self.fs_node_pk, expiration_time)
        time_offset = time_to_offset(expiration_time)

        self.assertFalse(validate_download_token(self.share_token, self.fs_node_pk, time_offset, signature))

    def test_invalid_signature(self):
        """Test that an invalid signature returns False."""
        expiration_time = now() + timedelta(hours=1)
        time_offset = time_to_offset(expiration_time)

        invalid_signature = "0" * 16
        self.assertFalse(validate_download_token(self.share_token, self.fs_node_pk, time_offset, invalid_signature))

    def test_invalid_signature_expired(self):
        """Test that an invalid signature + expired token returns False."""
        expiration_time = now() - timedelta(hours=1)
        time_offset = time_to_offset(expiration_time)

        invalid_signature = "0" * 16
        self.assertFalse(validate_download_token(self.share_token, self.fs_node_pk, time_offset, invalid_signature))


class ShareExpiryTests(ShareBaseTest):
    """Creating a share must support expiry, including updates without token rotation."""

    def setUp(self):
        """Create a second user for ownership tests."""
        super().setUp()
        self.other_user = UserFactory(username="share_expiry_other_user")

    @staticmethod
    def _create_url(path: str = "/root_dir") -> str:
        return reverse("share-create", kwargs={"path": path})

    def test_create_share_with_expiry(self):
        """An expiration supplied at creation time is stored and returned."""
        self.client.force_login(self.owner)
        expires_at = now() + timedelta(days=3)

        response = self.client.post(
            self._create_url(),
            data=json.dumps({"expires_at": expires_at.isoformat()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        share = SharedNode.objects.get(root_fs_node=self.root_dir)
        self.assertIsNotNone(share.expires_at)
        self.assertIsNotNone(response.json()["expires_at"])

    def test_create_share_with_invalid_expiry_is_rejected(self):
        """Malformed expiration values return a field validation error."""
        self.client.force_login(self.owner)

        response = self.client.post(
            self._create_url(),
            data=json.dumps({"expires_at": "not-a-date"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("expires_at", response.json()["detail"])

    def test_active_share_expiry_update_keeps_token(self):
        """Updating an active share's expiry must not rotate its public URL."""
        self.client.force_login(self.owner)
        share = create_public_share(self.owner, self.root_dir)
        token = share.token
        expires_at = now() + timedelta(days=5)

        response = self.client.post(
            self._create_url(),
            data=json.dumps({"expires_at": expires_at.isoformat()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        share.refresh_from_db()
        self.assertEqual(share.token, token)
        self.assertIsNotNone(share.expires_at)
        self.assertEqual(response.json()["id"], str(token))

    def test_expired_share_reactivation_rotates_token_and_sets_expiry(self):
        """Reactivating an expired share must invalidate the old URL and apply the new expiry."""
        self.client.force_login(self.owner)
        share = SharedNodeFactory(
            owner=self.owner,
            root_fs_node=self.root_dir,
            expires_at=now() - timedelta(days=1),
        )
        old_token = share.token
        expires_at = now() + timedelta(days=2)

        response = self.client.post(
            self._create_url(),
            data=json.dumps({"expires_at": expires_at.isoformat()}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        share.refresh_from_db()
        self.assertNotEqual(share.token, old_token)
        self.assertIsNone(share.revoked_at)
        self.assertIsNotNone(share.expires_at)
        self.assertGreater(share.expires_at, now())


class ShareListApiTests(ShareBaseTest):
    """The owner share list must be owner-scoped, filterable, and annotate stats."""

    def setUp(self):
        """Create one share for every lifecycle status plus another user's share."""
        super().setUp()
        self.other_user = UserFactory(username="share_list_other_user")
        self.active_share = SharedNodeFactory(
            owner=self.owner,
            root_fs_node=self.root_dir,
            expires_at=now() + timedelta(days=1),
        )
        self.revoked_share = SharedNodeFactory(
            owner=self.owner,
            root_fs_node=self.child_dir,
            revoked_at=now(),
            expires_at=now() - timedelta(days=1),
        )
        self.expired_share = SharedNodeFactory(
            owner=self.owner,
            root_fs_node=self.child_file,
            expires_at=now() - timedelta(days=1),
        )
        other_root = FsNodeDirectoryFactory(
            name="other-root",
            owner=self.other_user,
            storage=self.storage,
        )
        self.other_share = SharedNodeFactory(
            owner=self.other_user,
            root_fs_node=other_root,
        )

    @staticmethod
    def _list_url(**params) -> str:
        url = reverse("share-list")
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def test_list_is_owner_scoped(self):
        """Only the current user's shares are returned."""
        self.client.force_login(self.owner)

        response = self.client.get(self._list_url())

        self.assertEqual(response.status_code, 200)
        ids = {item["id"] for item in response.json()["items"]}
        self.assertEqual(ids, {
            str(self.active_share.token),
            str(self.revoked_share.token),
            str(self.expired_share.token),
        })
        self.assertNotIn(str(self.other_share.token), ids)

    def test_list_supports_status_filters(self):
        """All, active, revoked, and expired filters return only matching shares."""
        self.client.force_login(self.owner)

        expectations = {
            "all": {
                str(self.active_share.token),
                str(self.revoked_share.token),
                str(self.expired_share.token),
            },
            "active": {str(self.active_share.token)},
            "revoked": {str(self.revoked_share.token)},
            "expired": {str(self.expired_share.token)},
        }
        for status, expected_ids in expectations.items():
            with self.subTest(status=status):
                response = self.client.get(self._list_url(status=status))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {item["id"] for item in response.json()["items"]},
                    expected_ids,
                )

    def test_list_rejects_unknown_status(self):
        """An unknown status is reported as a field validation error."""
        self.client.force_login(self.owner)

        response = self.client.get(self._list_url(status="unknown"))

        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.json()["detail"])

    def test_list_includes_status_stats_and_minimal_node(self):
        """List items include download stats and only the root node identity."""
        self.client.force_login(self.owner)
        first_download = ShareDownload.objects.create(share=self.active_share)
        second_download = ShareDownload.objects.create(share=self.active_share)
        ShareDownload.objects.filter(pk=first_download.pk).update(
            created_at=now() - timedelta(hours=2),
        )
        ShareDownload.objects.filter(pk=second_download.pk).update(
            created_at=now() - timedelta(hours=1),
        )

        response = self.client.get(self._list_url())
        items = {item["id"]: item for item in response.json()["items"]}
        active_item = items[str(self.active_share.token)]
        revoked_item = items[str(self.revoked_share.token)]
        expired_item = items[str(self.expired_share.token)]

        self.assertEqual(active_item["status"], "active")
        self.assertEqual(revoked_item["status"], "revoked")
        self.assertEqual(expired_item["status"], "expired")
        self.assertEqual(active_item["download_count"], 2)
        self.assertIsNotNone(active_item["last_downloaded_at"])
        self.assertIn(f"/s/{self.active_share.token}/", active_item["url"])
        self.assertIsNone(revoked_item["url"])
        self.assertIsNone(expired_item["url"])
        self.assertEqual(
            set(active_item["root_fs_node"]),
            {"id", "name", "type", "path"},
        )

    def test_list_includes_full_node_paths(self):
        """Root and nested shared nodes expose their full owner-relative path."""
        self.client.force_login(self.owner)

        response = self.client.get(self._list_url())
        items = {item["id"]: item for item in response.json()["items"]}

        self.assertEqual(
            items[str(self.active_share.token)]["root_fs_node"]["path"],
            f"/{self.root_dir.name}",
        )
        self.assertEqual(
            items[str(self.revoked_share.token)]["root_fs_node"]["path"],
            f"/{self.root_dir.name}/{self.child_dir.name}",
        )
        self.assertEqual(
            items[str(self.expired_share.token)]["root_fs_node"]["path"],
            f"/{self.root_dir.name}/{self.child_file.name}",
        )
        self.assertNotIn(str(self.other_share.token), items)

    def test_list_pagination(self):
        """Page is honoured and page_size is fixed to the default."""
        self.client.force_login(self.owner)
        for index in range(30):
            node = FsNodeDirectoryFactory(
                name=f"pagination-{index}",
                owner=self.owner,
                storage=self.storage,
            )
            SharedNodeFactory(owner=self.owner, root_fs_node=node)

        first_page = self.client.get(self._list_url(page=1, page_size=2))
        second_page = self.client.get(self._list_url(page=2))

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(len(first_page.json()["items"]), 25)
        self.assertEqual(first_page.json()["page"], 1)
        self.assertEqual(first_page.json()["page_size"], 25)
        self.assertEqual(first_page.json()["total"], 33)
        self.assertTrue(first_page.json()["has_next"])
        self.assertEqual(len(second_page.json()["items"]), 8)
        self.assertFalse(second_page.json()["has_next"])

    def test_page_size_is_fixed(self):
        """The page size is fixed and not accepted from query parameters."""
        self.client.force_login(self.owner)

        response = self.client.get(self._list_url(page_size=1000))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page_size"], 25)

    def test_list_requires_authentication(self):
        """Anonymous users must not be able to list shares."""
        with self.assertRaises(Unauthorized):
            self.client.get(self._list_url())


class PermanentDeleteShareTests(ShareBaseTest):
    """Permanent deletion must be owner-scoped and cascade download history."""

    def setUp(self):
        """Create a share with one download and a second user."""
        super().setUp()
        self.other_user = UserFactory(username="share_delete_other_user")
        self.share = create_public_share(self.owner, self.root_dir)
        ShareDownload.objects.create(share=self.share)

    @staticmethod
    def _delete_url(share_token: str | uuid.UUID) -> str:
        return reverse("share-permanent-delete", kwargs={"share_token": str(share_token)})

    def test_owner_can_permanently_delete_share(self):
        """The owner can delete a share and its download history."""
        self.client.force_login(self.owner)

        response = self.client.delete(self._delete_url(self.share.token))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(SharedNode.objects.filter(pk=self.share.pk).exists())
        self.assertEqual(ShareDownload.objects.count(), 0)

    def test_owner_can_delete_revoked_share(self):
        """Permanent deletion is allowed for non-active shares as well."""
        self.client.force_login(self.owner)
        self.share.revoked_at = now()
        self.share.save(update_fields=["revoked_at"])

        response = self.client.delete(self._delete_url(self.share.token))

        self.assertEqual(response.status_code, 204)
        self.assertFalse(SharedNode.objects.filter(pk=self.share.pk).exists())

    def test_cannot_delete_another_users_share(self):
        """A user cannot permanently delete somebody else's share."""
        self.client.force_login(self.other_user)

        response = self.client.delete(self._delete_url(self.share.token))

        self.assertEqual(response.status_code, 404)
        self.assertTrue(SharedNode.objects.filter(pk=self.share.pk).exists())
        self.assertEqual(ShareDownload.objects.count(), 1)
