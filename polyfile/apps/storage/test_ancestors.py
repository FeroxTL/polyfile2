import uuid
from pathlib import PurePosixPath

from django.test import TestCase
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.accounts.factories import UserFactory
from polyfile.apps.share.factories import SharedNodeFactory
from polyfile.apps.storage.factories import (
    FsNodeDirectoryFactory,
    FsNodeFileFactory,
    StorageFactory,
)
from polyfile.apps.storage.managers import get_fs_node_ancestors
from polyfile.apps.storage.models import FsNode
from polyfile.apps.storage.utils import get_fs_node_with_children
from polyfile.core.exceptions import FsNodeNotFoundError


class FsNodeAncestorsTests(TestCase):
    """Pin `get_fs_node_ancestors()` ordering and subtree scoping."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )
        self.leaf = FsNodeFileFactory(
            name="leaf.txt", owner=self.user, storage=self.storage, parent=self.sub,
        )
        self.sibling = FsNodeDirectoryFactory(
            name="other", owner=self.user, storage=self.storage,
        )

    def test_ancestors_are_ordered_from_root_to_parent(self) -> None:
        self.assertEqual(
            [node.pk for node in get_fs_node_ancestors(self.user, self.leaf.pk)],
            [self.root.pk, self.sub.pk],
        )

    def test_root_node_has_no_ancestors(self) -> None:
        self.assertEqual(get_fs_node_ancestors(self.user, self.root.pk), [])

    def test_direct_child_has_single_ancestor(self) -> None:
        self.assertEqual(
            [node.pk for node in get_fs_node_ancestors(self.user, self.sub.pk)],
            [self.root.pk],
        )

    def test_stop_at_clips_the_chain(self) -> None:
        self.assertEqual(
            [node.pk for node in get_fs_node_ancestors(self.user, self.leaf.pk, stop_at=self.sub.pk)],
            [self.sub.pk],
        )

    def test_stop_at_the_node_itself_returns_no_ancestors(self) -> None:
        self.assertEqual(get_fs_node_ancestors(self.user, self.leaf.pk, stop_at=self.leaf.pk), [])

    def test_stop_at_full_tree_root_keeps_whole_chain(self) -> None:
        self.assertEqual(
            [node.pk for node in get_fs_node_ancestors(self.user, self.leaf.pk, stop_at=self.root.pk)],
            [self.root.pk, self.sub.pk],
        )

    def test_node_outside_subtree_returns_none(self) -> None:
        self.assertIsNone(get_fs_node_ancestors(self.user, self.sibling.pk, stop_at=self.root.pk))
        self.assertIsNone(get_fs_node_ancestors(self.user, self.root.pk, stop_at=self.sub.pk))

    def test_foreign_node_is_not_visible(self) -> None:
        other_user = UserFactory(storage=self.storage)
        foreign = FsNodeDirectoryFactory(name="foreign", owner=other_user, storage=self.storage)
        with self.assertRaises(FsNode.DoesNotExist):
            get_fs_node_ancestors(self.user, foreign.pk)

    def test_unknown_node_raises(self) -> None:
        with self.assertRaises(FsNode.DoesNotExist):
            get_fs_node_ancestors(self.user, uuid.uuid4())

    def test_ancestors_of_tombstoned_node_raise(self) -> None:
        FsNode.objects.filter(pk=self.leaf.pk).update(deleted_at=now())
        with self.assertRaises(FsNode.DoesNotExist):
            get_fs_node_ancestors(self.user, self.leaf.pk)

    def test_tombstoned_ancestor_is_pruned_from_the_chain(self) -> None:
        """Deletion tombstones whole subtrees, but a stale ancestor never leaks."""
        FsNode.objects.filter(pk=self.sub.pk).update(deleted_at=now())
        self.assertEqual(get_fs_node_ancestors(self.user, self.leaf.pk), [])


class FsNodeWithChildrenAncestorsTests(TestCase):
    """`get_fs_node_with_children()` must expose ancestors alongside the node."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )
        self.leaf = FsNodeFileFactory(
            name="leaf.txt", owner=self.user, storage=self.storage, parent=self.sub,
        )

    def test_virtual_root_has_no_identity_and_no_ancestors(self) -> None:
        result = get_fs_node_with_children(user=self.user, path=PurePosixPath("/"))
        self.assertIsNone(result.current.pk)
        self.assertEqual(list(result.ancestors), [])
        self.assertEqual([child.pk for child in result.children], [self.root.pk])

    def test_directory_ancestors_exclude_the_node_itself(self) -> None:
        result = get_fs_node_with_children(user=self.user, path=PurePosixPath("/root/sub"))
        self.assertEqual(result.current.pk, self.sub.pk)
        self.assertEqual([node.pk for node in result.ancestors], [self.root.pk])

    def test_file_ancestors_include_its_directory(self) -> None:
        result = get_fs_node_with_children(user=self.user, path=PurePosixPath("/root/sub/leaf.txt"))
        self.assertEqual(result.current.pk, self.leaf.pk)
        self.assertEqual([node.pk for node in result.ancestors], [self.root.pk, self.sub.pk])
        self.assertEqual(list(result.children), [])

    def test_share_root_hides_parent_identity(self) -> None:
        result = get_fs_node_with_children(
            user=self.user,
            path=PurePosixPath("/"),
            parent_fs_node=self.sub,
        )
        self.assertEqual(result.current.pk, self.sub.pk)
        self.assertIsNone(result.current.parent_id)

    def test_node_outside_share_is_not_found(self) -> None:
        with self.assertRaises(FsNodeNotFoundError):
            get_fs_node_with_children(
                user=self.user,
                path=PurePosixPath("/root"),
                parent_fs_node=self.sub,
            )


class FsNodeListApiAncestorsTests(TestCase):
    """The storage API response gains `id`, `parent_id` and `ancestors`."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.user = UserFactory(storage=self.storage)
        self.client.force_login(self.user)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.user, storage=self.storage)
        self.sub = FsNodeDirectoryFactory(
            name="sub", owner=self.user, storage=self.storage, parent=self.root,
        )
        self.leaf = FsNodeFileFactory(
            name="leaf.txt", owner=self.user, storage=self.storage, parent=self.sub,
        )

    def _get(self, path: str | None = None) -> dict:
        url = reverse("fs_node")
        response = self.client.get(url, {"path": path} if path is not None else {})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_root_response(self) -> None:
        data = self._get("/")
        self.assertIsNone(data["current"]["id"])
        self.assertNotIn("path", data["current"])
        self.assertEqual(data["ancestors"], [])
        self.assertEqual(
            [(child["name"], child["parent_id"]) for child in data["children"]],
            [("root", None)],
        )

    def test_default_path_is_root(self) -> None:
        self.assertEqual(self._get()["ancestors"], [])

    def test_nested_response_contains_ancestors(self) -> None:
        data = self._get("/root/sub")
        self.assertEqual(data["current"]["id"], str(self.sub.pk))
        self.assertEqual(data["current"]["parent_id"], str(self.root.pk))
        self.assertEqual(
            data["ancestors"],
            [{"id": str(self.root.pk), "name": "root"}],
        )

    def test_file_response_contains_ancestors(self) -> None:
        data = self._get("/root/sub/leaf.txt")
        self.assertEqual(data["current"]["id"], str(self.leaf.pk))
        self.assertEqual(
            data["ancestors"],
            [
                {"id": str(self.root.pk), "name": "root"},
                {"id": str(self.sub.pk), "name": "sub"},
            ],
        )

    def test_every_ancestor_is_addressable_by_id(self) -> None:
        """Each ancestor id identifies an active node of the same owner."""
        data = self._get("/root/sub/leaf.txt")
        for ancestor in data["ancestors"]:
            node = FsNode.active.get(pk=ancestor["id"])
            self.assertEqual(node.owner_id, self.user.pk)
            self.assertEqual(node.name, ancestor["name"])

    def test_missing_path_is_not_found(self) -> None:
        response = self.client.get(reverse("fs_node"), {"path": "/nope"})
        self.assertEqual(response.status_code, 404)


class ShareApiAncestorsTests(TestCase):
    """Public share responses must not leak ancestors above the share root."""

    def setUp(self) -> None:
        self.storage = StorageFactory()
        self.owner = UserFactory(storage=self.storage)
        self.root = FsNodeDirectoryFactory(name="root", owner=self.owner, storage=self.storage)
        self.shared = FsNodeDirectoryFactory(
            name="shared", owner=self.owner, storage=self.storage, parent=self.root,
        )
        self.nested = FsNodeDirectoryFactory(
            name="nested", owner=self.owner, storage=self.storage, parent=self.shared,
        )
        self.share = SharedNodeFactory(owner=self.owner, root_fs_node=self.shared)
        self.client.logout()

    @staticmethod
    def _url(share, path: str = "/") -> str:
        return reverse("share-api-detail-path", kwargs={"share_token": str(share.token), "path": path})

    def test_share_root_ancestors_are_clipped(self) -> None:
        data = self.client.get(self._url(self.share)).json()
        self.assertEqual(data["current"]["id"], str(self.shared.pk))
        self.assertEqual(data["ancestors"], [])
        self.assertIsNone(data["current"]["parent_id"])

    def test_nested_node_ancestors_stop_at_share_root(self) -> None:
        data = self.client.get(self._url(self.share, "/nested")).json()
        self.assertEqual(data["current"]["id"], str(self.nested.pk))
        self.assertEqual(data["ancestors"], [{"id": str(self.shared.pk), "name": "shared"}])

    def test_node_outside_share_is_not_found(self) -> None:
        response = self.client.get(self._url(self.share, "/../root"))
        self.assertEqual(response.status_code, 404)
