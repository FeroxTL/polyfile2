from django.test import TestCase
from django.urls import reverse

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.storage.factories import FsNodeDirectoryFactory, StorageFactory


class FsNodeBrowseInitialNodeTests(TestCase):
    """The embedded initial node lets the first page load use the node UUID."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )
        self.client.force_login(self.user)

    def get_initial_fs_node(self, path: str) -> dict:
        response = self.client.get(reverse("fs_node_browse", kwargs={"path": path}))
        self.assertEqual(response.status_code, 200)
        return response.context["initial_fs_node"]

    def test_embeds_the_node_id_for_a_directory(self) -> None:
        initial_fs_node = self.get_initial_fs_node("/root/sub/")

        self.assertEqual(initial_fs_node["node_id"], str(self.sub.pk))
        self.assertEqual(initial_fs_node["path"], "/root/sub/")

    def test_has_no_node_id_for_the_virtual_root(self) -> None:
        self.assertIsNone(self.get_initial_fs_node("/")["node_id"])

    def test_has_no_node_id_for_a_missing_path(self) -> None:
        self.assertIsNone(self.get_initial_fs_node("/missing/")["node_id"])

    def test_template_embeds_initial_fs_node_json(self) -> None:
        response = self.client.get(reverse("fs_node_browse", kwargs={"path": "/root/"}))
        self.assertContains(response, 'id="initial-fs-node"')
        self.assertContains(response, str(self.root.pk))


class FsNodeBrowseAuthTests(TestCase):
    def test_anonymous_users_are_redirected_to_login(self) -> None:
        response = self.client.get(reverse("fs_node_browse", kwargs={"path": "/"}))

        self.assertEqual(response.status_code, 302)
