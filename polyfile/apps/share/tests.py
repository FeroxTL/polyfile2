import tempfile
import uuid
from datetime import timedelta
from unittest import mock

from django.core.files.base import ContentFile
from django.http.response import StreamingHttpResponse
from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.share.models import SharedNode
from polyfile.apps.share.services import create_public_share
from polyfile.apps.share.utils import (
    share_download_url,
)
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.models import FsNode
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path


class ShareBaseTest(TestCase):
    """Shared fixtures for share tests."""

    def setUp(self) -> None:
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
    def setUp(self) -> None:
        """Test setUp."""
        super().setUp()
        self.other_user = UserFactory(username="other_user")

    @staticmethod
    def _create_url(path: str = "/root_dir") -> str:
        return reverse("share-create", kwargs={"path": path})

    def test_create_share_success(self) -> None:
        """Verify that user_a can create a share for root_dir."""
        share = create_public_share(self.owner, self.root_dir)

        self.assertIsInstance(share, SharedNode)
        self.assertEqual(share.owner, self.owner)
        self.assertEqual(share.root_fs_node, self.root_dir)

    def test_create_share_unauthorized(self) -> None:
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

    def test_create_share_not_found(self) -> None:
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

    def test_create_share_for_root_is_rejected(self) -> None:
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

    def test_reactivate_revoked_share(self) -> None:
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

    def test_create_share_keeps_active_token(self) -> None:
        """Repeated create requests for an active share return the same link."""
        self.client.force_login(self.owner)

        first = self.client.post(self._create_url())
        second = self.client.post(self._create_url())

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(SharedNode.objects.count(), 1)

    def test_create_share_view(self) -> None:
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

    def setUp(self) -> None:
        """Create an active share and a second user."""
        super().setUp()
        self.other_user = UserFactory(username="share_other_user")
        self.share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)

    @staticmethod
    def _revoke_url(share_token: str | uuid.UUID) -> str:
        return reverse("share-api-revoke", kwargs={"share_token": str(share_token)})

    def test_revoke_share_is_a_soft_delete(self) -> None:
        """A successful revoke keeps the row but marks it as revoked."""
        self.client.force_login(self.owner)

        response = self.client.post(self._revoke_url(self.share.token))

        self.assertEqual(response.status_code, 204)
        self.share.refresh_from_db()
        self.assertIsNotNone(self.share.revoked_at)
        self.assertFalse(self.share.is_active)
        self.assertEqual(SharedNode.objects.count(), 1)

    def test_revoke_share_is_idempotent(self) -> None:
        """Revoking an already revoked share keeps the original timestamp."""
        self.client.force_login(self.owner)

        self.assertEqual(self.client.post(self._revoke_url(self.share.token)).status_code, 204)
        self.share.refresh_from_db()
        revoked_at = self.share.revoked_at
        
        self.assertEqual(self.client.post(self._revoke_url(self.share.token)).status_code, 204)
        self.share.refresh_from_db()
        self.assertEqual(self.share.revoked_at, revoked_at)

    def test_revoke_share_of_another_user_is_not_found(self) -> None:
        """A user cannot revoke somebody else's share by guessing its token."""
        self.client.force_login(self.other_user)

        response = self.client.post(self._revoke_url(self.share.token))

        self.assertEqual(response.status_code, 404)
        self.share.refresh_from_db()
        self.assertIsNone(self.share.revoked_at)

    def test_revoked_share_url_stops_working(self) -> None:
        """The old public URL must return 404 immediately after revocation."""
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(self._revoke_url(self.share.token)).status_code, 204)
        self.client.logout()

        response = self.client.get(reverse(
            "share-api-detail-path",
            kwargs={"share_token": str(self.share.token), "path": "/"},
        ))

        self.assertEqual(response.status_code, 404)

    def test_recreate_after_revoke_rotates_token(self) -> None:
        """Sharing again after revoke returns a new link and no longer revoked share."""
        self.client.force_login(self.owner)
        old_token = self.share.token
        self.assertEqual(self.client.post(self._revoke_url(old_token)).status_code, 204)

        response = self.client.post(reverse(
            "share-create",
            kwargs={"path": f"/{self.root_dir.name}"},
        ))

        self.share.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(self.share.token, old_token)
        self.assertEqual(response.json()["id"], str(self.share.token))
        self.assertIsNone(self.share.revoked_at)
        self.assertTrue(self.share.is_active)


class ShareActiveManagerTests(TestCase):
    """
    Pin the expiry semantics of ``SharedNode.active`` (defect D6).

    The manager and the ``is_active`` property must agree. Today the manager's filter is
    ``expires_at__lte=now``, which *excludes* every share that has not expired yet, so a
    valid non-expiring-in-the-future share is invisible to ``.active.get()`` and the whole
    share API answers 404.
    """

    def test_share_without_expiry_is_active(self) -> None:
        """A share with no ``expires_at`` is active and visible through the manager."""
        share = SharedNodeFactory(expires_at=None)

        self.assertEqual(SharedNode.active.get(token=share.token), share)
        self.assertTrue(share.is_active)
        self.assertIsNone(share.expires_at)

    def test_share_with_future_expiry_is_active(self) -> None:
        """A share with a future ``expires_at`` is active and visible through the manager."""
        share = SharedNodeFactory(expires_at=now() + timedelta(days=1))

        self.assertTrue(share.is_active)
        self.assertEqual(SharedNode.active.get(token=share.token), share)
        self.assertTrue(share.expires_at > now())

    def test_share_expired_in_the_past_is_inactive(self) -> None:
        """A share whose ``expires_at`` has passed is not active."""
        share = SharedNodeFactory(expires_at=now() - timedelta(days=1))

        self.assertFalse(share.is_active)
        self.assertTrue(share.expires_at < now())
        with self.assertRaises(SharedNode.DoesNotExist):
            SharedNode.active.get(token=share.token)

    def test_revoked_share(self) -> None:
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
        """Check download directory in share."""
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
        file_response.close()

    def test_child_details_are_publicly_accessible(self) -> None:
        """Check that anonymous visitor gets the root node and its children in payload."""
        share = SharedNodeFactory(owner=self.owner, root_fs_node=self.root_dir)
        nested_node = FsNodeFileFactory(
            name="notes1.txt",
            owner=self.owner,
            size=5,
            storage=self.storage,
            parent=self.child_dir,
        )
        nested_node.file.save("notes1.txt", ContentFile(b"hello"), save=True)

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
                        "created_at": nested_node.created_at.isoformat(),
                        "download_url": mock.ANY,
                        "file": nested_node.file.name,
                        "md5": nested_node.md5,
                        "mime_type": nested_node.mime_type,
                        "modified_at": nested_node.modified_at.isoformat(),
                        "name": nested_node.name,
                        "size": nested_node.size,
                        "type": FsNode.TypeChoices.FILE.value,
                    },
                ],
            },
        )

        file_response = self.client.get(response.json()["children"][0]["download_url"])
        self.assertIsInstance(file_response, StreamingHttpResponse)
        file_response.close()
