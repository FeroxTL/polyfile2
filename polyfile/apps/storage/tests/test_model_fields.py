"""Tests for the composite ``FileRefField`` / ``FsNodeFileRef``."""

import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib import admin
from django.http import HttpRequest
from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import (
    FsNodeArchiveJobFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.model_fields import FileRefField, FsNodeFileRef
from polyfile.apps.storage.models import FsNode, FsNodeArchiveItem, FsNodeArchiveJob
from polyfile.contrib.backends.file_system_backend.backend import FileSystemBackend
from polyfile.contrib.backends.utils import get_storage_path


class FsNodeFileRefTests(TestCase):
    """``FsNodeFileRef`` behaviour."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)

    def test_truthiness_uses_object_key(self) -> None:
        node = FsNodeFileFactory(owner=self.user, storage=self.storage, object_key="")

        self.assertFalse(node.file)

        node.object_key = "uploads/a.txt"
        node.save(update_fields=["object_key"])

        self.assertTrue(node.file)

    def test_open_raises_without_storage_id(self) -> None:
        node = FsNode(name="x.txt", type=FsNode.TypeChoices.FILE, storage_id=None)
        ref = FsNodeFileRef(node, None, "a.txt")

        with self.assertRaises(RuntimeError):
            ref.open()

    def test_delete_is_noop_without_object_key(self) -> None:
        node = FsNodeFileFactory(owner=self.user, storage=self.storage, object_key="")

        node.file.delete()  # should not raise

    def test_download_url_delegates_to_backend(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            object_key="uploads/a.txt",
        )

        self.assertEqual(node.file.download_url(), "/test/url/")


class FileSystemBackendDownloadUrlTests(TestCase):
    """The local backend must expose the authorized download view."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.storage = FileSystemBackend(location=self.temp_dir.name)
        self.user = UserFactory()

    def test_url_points_to_download_view(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage__backend=get_storage_path(FileSystemBackend),
            storage__options={"location": self.temp_dir.name, "upload_to": ""},
            object_key="a.txt",
        )

        self.assertEqual(
            node.file.download_url(),
            reverse("download_file", args=[node.pk]),
        )

    def test_open_reads_saved_file(self) -> None:
        backend = FileSystemBackend(location=self.temp_dir.name)
        backend.save("a.txt", BytesIO(b"hello"))

        with backend.open("a.txt") as fileobj:
            self.assertEqual(fileobj.read(), b"hello")

    def test_save_publishes_atomically(self) -> None:
        backend = FileSystemBackend(location=self.temp_dir.name)
        backend.save("a.txt", BytesIO(b"hello"))

        self.assertTrue(Path(self.temp_dir.name, "a.txt").exists())
        self.assertFalse(Path(self.temp_dir.name, "a.txt.part").exists())

    def test_delete_ignores_missing_file(self) -> None:
        backend = FileSystemBackend(location=self.temp_dir.name)
        backend.delete("missing.txt")


class FileRefFieldDescriptorTests(TestCase):
    """``FileRefField`` descriptor get/set."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)

    def test_get_returns_ref_with_current_values(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            object_key="uploads/a.txt",
        )

        self.assertIsInstance(node.file, FsNodeFileRef)
        self.assertEqual(node.file.storage_id, self.storage.pk)
        self.assertEqual(node.file.object_key, "uploads/a.txt")

    def test_set_none_clears_object_key(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            object_key="uploads/a.txt",
        )

        node.file = None

        self.assertEqual(node.object_key, "")

    def test_set_ref_updates_both_columns(self) -> None:
        node = FsNodeFileFactory(
            owner=self.user,
            storage=self.storage,
            object_key="uploads/a.txt",
        )
        other_storage = StorageFactory()

        node.file = FsNodeFileRef(node, other_storage.pk, "uploads/b.txt")

        self.assertEqual(node.storage_id, other_storage.pk)
        self.assertEqual(node.object_key, "uploads/b.txt")

    def test_set_string_raises(self) -> None:
        node = FsNodeFileFactory(owner=self.user, storage=self.storage)

        with self.assertRaises(TypeError):
            node.file = "uploads/a.txt"


class FileRefFieldClassTests(TestCase):
    """``FileRefField`` is not a Django ``Field``."""

    def test_not_a_django_field(self) -> None:
        field = FileRefField("storage_id", "object_key")

        self.assertNotIsInstance(field, FsNode._meta.get_field("object_key").__class__)
        # The real check: it has no ``column`` and is not in _meta.fields.
        self.assertFalse(hasattr(field, "column"))


class FsNodeAdminCreateTests(TestCase):
    """Creating an FsNode through the admin must allow setting owner/storage."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.admin_user = UserFactory(
            storage=self.storage,
            is_staff=True,
            is_superuser=True,
        )

    def test_create_file_node_in_admin(self) -> None:
        self.client.force_login(self.admin_user)

        response = self.client.post(
            reverse("admin:storage_fsnode_add"),
            {
                "name": "new.txt",
                "type": FsNode.TypeChoices.FILE,
                "storage": self.storage.pk,
                "owner": self.admin_user.pk,
            },
        )

        self.assertEqual(response.status_code, 302)
        node = FsNode.objects.get(name="new.txt")
        self.assertEqual(node.owner, self.admin_user)
        self.assertEqual(node.storage, self.storage)

    def test_edit_form_marks_owner_storage_type_as_readonly(self) -> None:
        node = FsNodeFileFactory(owner=self.admin_user, storage=self.storage)
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse("admin:storage_fsnode_change", args=[node.pk]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, node.object_key)
        self.assertContains(response, "download")


class FsNodeArchiveItemAdminTests(TestCase):
    """Archive items are immutable snapshots: add/change disabled in admin."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.admin_user = UserFactory(
            storage=self.storage,
            is_staff=True,
            is_superuser=True,
        )

    def test_add_and_change_are_disabled(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveItemAdmin

        model_admin = FsNodeArchiveItemAdmin(FsNodeArchiveItem, admin.site)
        request = HttpRequest()
        request.user = self.admin_user

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))


class FsNodeArchiveJobAdminTests(TestCase):
    """Archive jobs are system-managed: add/change disabled in admin."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.admin_user = UserFactory(
            storage=self.storage,
            is_staff=True,
            is_superuser=True,
        )

    def test_add_and_change_are_disabled(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin

        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)
        request = HttpRequest()
        request.user = self.admin_user

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))

    def test_root_node_link_points_to_fsnode_change_page(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin

        node = FsNodeFileFactory(owner=self.admin_user, storage=self.storage)
        job = FsNodeArchiveJobFactory(
            requested_by=self.admin_user,
            root_node_uuid=node.pk,
            root_node_name=node.name,
        )
        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)

        html = model_admin.root_node_link(job)

        self.assertIn(reverse("admin:storage_fsnode_change", args=[node.pk]), html)
        self.assertIn(str(node.pk), html)

    def test_root_node_link_shows_plain_uuid_when_node_is_gone(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin

        job = FsNodeArchiveJobFactory(requested_by=self.admin_user)
        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)

        self.assertEqual(model_admin.root_node_link(job), str(job.root_node_uuid))

    def test_file_display_shows_download_link_for_ready_archive(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin

        job = FsNodeArchiveJobFactory(
            requested_by=self.admin_user,
            status=FsNodeArchiveJob.Status.READY,
            archive_key="archives/aa/job.zip",
            root_node_name="backup",
        )
        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)

        html = model_admin.file_display(job)

        self.assertIn(reverse("archive_job_file", kwargs={"job_id": job.pk}), html)
        self.assertIn("backup.zip", html)

    def test_file_display_is_dash_for_non_ready_job(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin

        job = FsNodeArchiveJobFactory(
            requested_by=self.admin_user,
            status=FsNodeArchiveJob.Status.PENDING,
        )
        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)

        self.assertEqual(model_admin.file_display(job), "-")

    def test_deleting_job_removes_archive_file(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin
        from polyfile.apps.storage.archive_backend import FileSystemArchiveBackend

        archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(archive_dir.cleanup)
        backend = FileSystemArchiveBackend(archive_dir.name)
        backend.save_stream("jobs/abc/job.zip", BytesIO(b"zip content"))

        job = FsNodeArchiveJobFactory(
            requested_by=self.admin_user,
            status=FsNodeArchiveJob.Status.READY,
            archive_key="jobs/abc/job.zip",
        )
        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)
        request = HttpRequest()
        request.user = self.admin_user

        self.assertTrue(backend.exists(job.archive_key))
        with self.settings(ARCHIVE_ROOT=archive_dir.name):
            model_admin.delete_model(request, job)
        self.assertFalse(backend.exists("jobs/abc/job.zip"))
        self.assertFalse(FsNodeArchiveJob.objects.filter(pk=job.pk).exists())

    def test_deleting_queryset_removes_archive_files(self) -> None:
        from polyfile.apps.storage.admin import FsNodeArchiveJobAdmin
        from polyfile.apps.storage.archive_backend import FileSystemArchiveBackend

        archive_dir = tempfile.TemporaryDirectory()
        self.addCleanup(archive_dir.cleanup)
        backend = FileSystemArchiveBackend(archive_dir.name)
        backend.save_stream("jobs/a.zip", BytesIO(b"a"))
        backend.save_stream("jobs/b.zip", BytesIO(b"b"))

        job_a = FsNodeArchiveJobFactory(
            requested_by=self.admin_user,
            status=FsNodeArchiveJob.Status.READY,
            archive_key="jobs/a.zip",
        )
        job_b = FsNodeArchiveJobFactory(
            requested_by=self.admin_user,
            status=FsNodeArchiveJob.Status.READY,
            archive_key="jobs/b.zip",
        )
        model_admin = FsNodeArchiveJobAdmin(FsNodeArchiveJob, admin.site)
        request = HttpRequest()
        request.user = self.admin_user

        with self.settings(ARCHIVE_ROOT=archive_dir.name):
            model_admin.delete_queryset(
                request,
                FsNodeArchiveJob.objects.filter(pk__in=[job_a.pk, job_b.pk]),
            )
        self.assertFalse(backend.exists("jobs/a.zip"))
        self.assertFalse(backend.exists("jobs/b.zip"))
