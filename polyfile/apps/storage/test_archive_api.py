import hashlib
import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path

from django.core.management import call_command
from django.http.response import FileResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.share.services import revoke_public_share
from polyfile.apps.share.utils import share_archive_url, share_download_url
from polyfile.apps.storage.archive import create_archive_job
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
)
from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.models import FsNodeArchiveJob, FsStorage
from polyfile.apps.storage.utils import remove_fs_node
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path


class ArchiveApiTestBase(TestCase):
    """Fixtures shared by archive delivery tests."""

    def setUp(self) -> None:
        self.source_dir = tempfile.TemporaryDirectory()
        self.archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.source_dir.cleanup)
        self.addCleanup(self.archive_dir.cleanup)

        self.settings_override = override_settings(
            ARCHIVE_ROOT=Path(self.archive_dir.name),
            ARCHIVE_ACCEL_PREFIX="",
            DIRECTORY_ARCHIVE_TTL=timedelta(hours=2),
            DIRECTORY_ARCHIVE_RETRY_AFTER=2,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.storage = FsStorage.objects.create(
            name="Local disk",
            backend=get_storage_path(FileSystemBackend),
            options={"location": self.source_dir.name, "upload_to": ""},
        )
        fs_storages.clear()
        self.addCleanup(fs_storages.clear)

        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(
            name="root",
            owner=self.user,
            storage=self.storage,
        )
        self.subdir = FsNodeDirectoryFactory(
            name="sub",
            owner=self.user,
            storage=self.storage,
            parent=self.root,
        )
        self.file1 = self._create_file("a.txt", b"aaa", parent=self.root)
        self.file2 = self._create_file(
            "b.txt",
            b"bbbb",
            parent=self.subdir,
            relative_path="sub/b.txt",
        )

    def _create_file(
        self,
        name: str,
        content: bytes,
        parent,
        relative_path: str | None = None,
    ):
        relative_path = relative_path or name
        path = Path(self.source_dir.name, relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return FsNodeFileFactory(
            name=name,
            object_key=relative_path,
            owner=self.user,
            storage=self.storage,
            parent=parent,
            size=len(content),
            md5=hashlib.md5(content).hexdigest(),
        )

    def _run_worker(self) -> None:
        call_command(
            "run_archive_worker",
            "--once",
            stdout=StringIO(),
            stderr=StringIO(),
        )

    def _archive_path(self, job: FsNodeArchiveJob) -> Path:
        return Path(self.archive_dir.name, job.archive_key)

    def _zip_content(self, response) -> bytes:
        return b"".join(response.streaming_content)


class ArchiveApiTests(ArchiveApiTestBase):
    def test_list_exposes_archive_url_for_directories(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("fs_node"), {"path": "/"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # The top-level "/" entry is a virtual root and has no archive URL.
        self.assertEqual(data["current"]["download_url"], "")
        children = {child["name"]: child for child in data["children"]}
        self.assertEqual(
            children[self.root.name]["download_url"],
            reverse("download_file", args=[self.root.pk]),
        )

        nested_response = self.client.get(
            reverse("fs_node"),
            {"path": f"/{self.root.name}"},
        )
        nested_children = {
            child["name"]: child for child in nested_response.json()["children"]
        }
        self.assertEqual(
            nested_children[self.subdir.name]["download_url"],
            reverse("download_file", args=[self.subdir.pk]),
        )
        self.assertTrue(nested_children[self.file1.name]["download_url"])

    def test_directory_download_starts_job_and_redirects(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(reverse("download_file", args=[self.root.pk]))

        self.assertEqual(response.status_code, 303)
        job = FsNodeArchiveJob.objects.get()
        self.assertEqual(
            response["Location"],
            reverse("archive_job_wait", args=[job.pk]),
        )
        self.assertEqual(job.status, FsNodeArchiveJob.Status.PENDING)
        self.assertEqual(job.requested_by, self.user)
        self.assertEqual(job.items.count(), 3)

    def test_directory_download_json_returns_202_and_polling_urls(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("download_file", args=[self.root.pk]),
            {"format": "json"},
        )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response["Retry-After"], "2")
        self.assertEqual(response["Cache-Control"], "no-store")
        data = response.json()
        self.assertEqual(data["status"], FsNodeArchiveJob.Status.PENDING)
        self.assertEqual(data["retry_after"], 2)
        self.assertIsNone(data["file_url"])
        self.assertEqual(
            data["status_url"],
            f"http://testserver{reverse('archive_job_status', args=[data['job_id']])}",
        )
        self.assertEqual(response["Location"], data["status_url"])

    def test_status_and_file_report_pending(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)

        status_response = self.client.get(
            reverse("archive_job_status", args=[job.pk]),
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response["Retry-After"], "2")
        self.assertEqual(
            status_response.json()["status"],
            FsNodeArchiveJob.Status.PENDING,
        )

        file_response = self.client.get(reverse("archive_job_file", args=[job.pk]))
        self.assertEqual(file_response.status_code, 202)
        self.assertEqual(file_response["Retry-After"], "2")
        self.assertEqual(
            file_response.json()["status"],
            FsNodeArchiveJob.Status.PENDING,
        )

    def test_ready_archive_is_served_as_attachment(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        job.refresh_from_db()

        status_response = self.client.get(
            reverse("archive_job_status", args=[job.pk]),
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(
            status_response.json()["status"],
            FsNodeArchiveJob.Status.READY,
        )
        self.assertIsNotNone(status_response.json()["file_url"])

        response = self.client.get(reverse("archive_job_file", args=[job.pk]))

        self.assertIsInstance(response, FileResponse)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("root.zip", response["Content-Disposition"])

        content = self._zip_content(response)
        response.close()
        self.assertEqual(content, self._archive_path(job).read_bytes())
        with zipfile.ZipFile(BytesIO(content)) as archive:
            self.assertEqual(archive.read("a.txt"), b"aaa")
            self.assertEqual(archive.read("sub/b.txt"), b"bbbb")

        job.refresh_from_db()
        self.assertIsNotNone(job.last_accessed_at)

    def test_head_ready_archive_does_not_stream_the_file(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        job.refresh_from_db()

        response = self.client.head(reverse("archive_job_file", args=[job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("root.zip", response["Content-Disposition"])
        self.assertEqual(response.content, b"")

        job.refresh_from_db()
        self.assertIsNone(job.last_accessed_at)

    def test_head_missing_archive_file_returns_410(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        job.refresh_from_db()
        self._archive_path(job).unlink()

        response = self.client.head(reverse("archive_job_file", args=[job.pk]))

        self.assertEqual(response.status_code, 410)

    @override_settings(ARCHIVE_ACCEL_PREFIX="/_archives/")
    def test_accel_redirect_is_used_when_configured(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        job.refresh_from_db()

        response = self.client.get(reverse("archive_job_file", args=[job.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Accel-Redirect"],
            f"/_archives/{job.archive_key}",
        )
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertEqual(response.content, b"")

    def test_expired_archive_is_gone(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        FsNodeArchiveJob.objects.filter(pk=job.pk).update(
            expires_at=now() - timedelta(seconds=1),
        )

        status_response = self.client.get(
            reverse("archive_job_status", args=[job.pk]),
        )
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(
            status_response.json()["status"],
            FsNodeArchiveJob.Status.EXPIRED,
        )
        self.assertIsNone(status_response.json()["file_url"])

        file_response = self.client.get(reverse("archive_job_file", args=[job.pk]))
        self.assertEqual(file_response.status_code, 410)
        self.assertEqual(
            file_response.json()["error_id"],
            "ArchiveUnavailable",
        )
        self.assertEqual(
            file_response.json()["message"],
            "Archive expired.",
        )

        wait_response = self.client.get(reverse("archive_job_wait", args=[job.pk]))
        self.assertEqual(wait_response.status_code, 410)

    def test_deleted_root_invalidates_the_job(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        remove_fs_node(self.user, self.root.pk)

        status_response = self.client.get(
            reverse("archive_job_status", args=[job.pk]),
        )
        self.assertEqual(status_response.status_code, 410)

        file_response = self.client.get(reverse("archive_job_file", args=[job.pk]))
        self.assertEqual(file_response.status_code, 410)

        new_request = self.client.get(reverse("download_file", args=[self.root.pk]))
        self.assertEqual(new_request.status_code, 404)

    def test_other_user_cannot_access_the_job(self) -> None:
        other_user = UserFactory()
        self.client.force_login(other_user)
        job = create_archive_job(self.user, self.root)

        self.assertEqual(
            self.client.get(reverse("archive_job_status", args=[job.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse("archive_job_file", args=[job.pk])).status_code,
            404,
        )

    def test_other_user_cannot_probe_a_deleted_job(self) -> None:
        job = create_archive_job(self.user, self.root)
        remove_fs_node(self.user, self.root.pk)

        other_user = UserFactory()
        self.client.force_login(other_user)

        response = self.client.get(
            reverse("archive_job_status", args=[job.pk]),
        )

        self.assertEqual(response.status_code, 404)

    def test_unknown_job_returns_404(self) -> None:
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("archive_job_status", args=["00000000-0000-0000-0000-000000000000"]),
        )

        self.assertEqual(response.status_code, 404)

    def test_missing_archive_file_returns_410(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        job.refresh_from_db()
        self._archive_path(job).unlink()

        response = self.client.get(reverse("archive_job_file", args=[job.pk]))

        self.assertEqual(response.status_code, 410)
        self.assertIn("Accept", response["Vary"])
        self.assertEqual(
            response.json()["error_id"],
            "ArchiveUnavailable",
        )
        self.assertEqual(
            response.json()["message"],
            "The archive file is no longer available.",
        )

    def test_missing_archive_file_renders_html_for_browser(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        self._run_worker()
        job.refresh_from_db()
        self._archive_path(job).unlink()

        response = self.client.get(
            reverse("archive_job_file", args=[job.pk]),
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, 410)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("Accept", response["Vary"])
        self.assertContains(response, "No longer available", status_code=410)
        self.assertContains(
            response,
            "The archive file is no longer available.",
            status_code=410,
        )

    def test_permission_error_renders_html_for_browser(self) -> None:
        other_user = UserFactory()
        self.client.force_login(other_user)

        response = self.client.get(
            reverse("download_file", args=[self.root.pk]),
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("Accept", response["Vary"])
        self.assertContains(response, "Access denied", status_code=403)

    def test_status_error_renders_html_for_browser(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)
        remove_fs_node(self.user, self.root.pk)

        response = self.client.get(
            reverse("archive_job_status", args=[job.pk]),
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, 410)
        self.assertContains(response, "No longer available", status_code=410)

    def test_wait_page_renders_then_redirects_when_ready(self) -> None:
        self.client.force_login(self.user)
        job = create_archive_job(self.user, self.root)

        response = self.client.get(reverse("archive_job_wait", args=[job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Preparing your archive")
        self.assertContains(response, "archive-progress")
        self.assertContains(response, "archive-title")
        self.assertContains(response, "Your archive is ready")
        self.assertContains(response, "The download will start automatically")
        self.assertContains(response, "archive-download")

        self._run_worker()
        response = self.client.get(reverse("archive_job_wait", args=[job.pk]))
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response["Location"],
            reverse("archive_job_file", args=[job.pk]),
        )


class ShareArchiveApiTests(ArchiveApiTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.share = SharedNodeFactory(
            root_fs_node=self.root,
            owner=self.user,
        )
        self.client.logout()

    def _job(self) -> FsNodeArchiveJob:
        return FsNodeArchiveJob.objects.get()

    def test_share_directory_download_redirects_to_wait_page(self) -> None:
        response = self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )

        self.assertEqual(response.status_code, 303)
        job = self._job()
        self.assertIn(f"/s/archive/{self.share.token}/{job.pk}/", response["Location"])

    def test_share_archive_flow_serves_zip_and_logs_download(self) -> None:
        response = self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )
        wait_url = response["Location"]
        job = self._job()

        wait_response = self.client.get(wait_url)
        self.assertEqual(wait_response.status_code, 200)
        self.assertContains(wait_response, "Preparing your archive")

        self._run_worker()
        wait_response = self.client.get(wait_url)
        self.assertEqual(wait_response.status_code, 303)
        file_url = wait_response["Location"]

        file_response = self.client.get(file_url)
        self.assertIsInstance(file_response, FileResponse)
        content = self._zip_content(file_response)
        file_response.close()

        with zipfile.ZipFile(BytesIO(content)) as archive:
            self.assertEqual(archive.read("a.txt"), b"aaa")

        self.assertEqual(self.share.downloads.count(), 1)
        job.refresh_from_db()
        self.assertEqual(job.status, FsNodeArchiveJob.Status.READY)

    def test_share_archive_head_does_not_log_a_download(self) -> None:
        response = self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )
        wait_url = response["Location"]

        self._run_worker()
        wait_response = self.client.get(wait_url)
        file_url = wait_response["Location"]

        head_response = self.client.head(file_url)

        self.assertEqual(head_response.status_code, 200)
        self.assertEqual(head_response.content, b"")
        self.assertEqual(self.share.downloads.count(), 0)

    def test_share_archive_file_error_renders_html_for_browser(self) -> None:
        response = self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )
        wait_url = response["Location"]

        self._run_worker()
        wait_response = self.client.get(wait_url)
        file_url = wait_response["Location"]
        self._archive_path(self._job()).unlink()

        response = self.client.get(file_url, HTTP_ACCEPT="text/html")

        self.assertEqual(response.status_code, 410)
        self.assertIn("Accept", response["Vary"])
        self.assertContains(
            response,
            "The archive file is no longer available.",
            status_code=410,
        )

    def test_share_archive_status_is_json(self) -> None:
        response = self.client.get(
            share_download_url(self.share.token, self.root.pk),
            {"format": "json"},
        )
        self.assertEqual(response.status_code, 202)
        status_url = response.json()["status_url"]

        status_response = self.client.get(status_url)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(
            status_response.json()["status"],
            FsNodeArchiveJob.Status.PENDING,
        )
        self.assertEqual(status_response["Retry-After"], "2")

    def test_revoked_share_job_url_is_gone(self) -> None:
        self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )
        job = self._job()
        status_url = share_archive_url(
            "share-archive-status",
            self.share.token,
            self.root.pk,
            job.pk,
        )

        revoke_public_share(self.user, self.share.token)

        status_response = self.client.get(status_url)
        self.assertEqual(status_response.status_code, 410)
        self.assertEqual(status_response.json()["error_id"], "ArchiveUnavailable")

        new_request = self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )
        self.assertEqual(new_request.status_code, 404)

    def test_invalid_share_archive_signature_is_404(self) -> None:
        response = self.client.get(
            share_download_url(self.share.token, self.root.pk),
        )
        wait_url = response["Location"]
        signature = wait_url.rstrip("/").rsplit("/", 1)[-1]
        tampered_url = wait_url.replace(signature, "bad")

        self.assertEqual(self.client.get(tampered_url).status_code, 404)
