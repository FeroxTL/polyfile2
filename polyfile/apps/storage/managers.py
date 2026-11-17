import uuid
from functools import partial
from pathlib import PurePosixPath

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django_cte import CTE, with_cte

from polyfile.apps.storage.models import FsNode


def get_fs_node_by_path_name(
        user: AbstractBaseUser,
        path: PurePosixPath,
        parent_fs_node: FsNode | None = None,
) -> FsNode | None:
    """
    Resolve a node by walking its path segments from a parent (or the root).

    Each step is a single indexed lookup on ``(owner, parent, name)``, so the
    cost is O(depth) instead of a recursive CTE over the whole tree.

    :param user: The AbstractBaseUser instance of the FsNode owner.
    :param path: The PurePosixPath to search for.
    :param parent_fs_node: Optional FsNode. If provided, the search starts at
                           its direct children (path is then relative to it).
    :return: The FsNode instance if found, otherwise the parent (for "/").
    :raises FsNode.DoesNotExist: If any segment does not resolve to a node.
    """
    if path == PurePosixPath('/'):
        return parent_fs_node

    node = parent_fs_node
    for name in path.parts[1:] if path.is_absolute() else path.parts:
        lookup = {"owner": user, "name": name}
        if node is None:
            lookup["parent__isnull"] = True
        else:
            lookup["parent"] = node
        node = FsNode.active.get(**lookup)
    return node


def make_fs_node_ancestor_cte(cte: CTE, base_queryset: models.QuerySet, node_id: uuid.UUID) -> models.QuerySet:
    """
    Construct a recursive CTE that walks the parent chain upwards from a node.

    The base part is the node itself (depth 0); each recursive step adds its
    parent with depth + 1. The chain naturally ends at a root (parent is NULL).

    :param cte: The CTE object.
    :param base_queryset: Owner-scoped QuerySet of active FsNode objects.
    :param node_id: The UUID of the node to start from.
    """
    qs = base_queryset.filter(id=node_id).values(
        'id',
        'parent_id',
        depth=models.Value(0, output_field=models.IntegerField()),
    )

    return qs.union(
        cte.join(base_queryset, id=cte.col.parent_id).values(
            'id',
            'parent_id',
            depth=cte.col.depth + models.Value(1),
        ),
        all=True,
    )


def get_fs_node_ancestors(
        user: AbstractBaseUser,
        node_id: uuid.UUID,
        stop_at: uuid.UUID | None = None,
) -> list[FsNode] | None:
    """
    Retrieve the ancestors of a node, ordered from the (sub)root to its parent.

    When ``stop_at`` is given, the result is clipped to that subtree boundary:
    it starts at the ``stop_at`` node and never exposes nodes above it (public
    share scoping). ``stop_at`` itself is included, the node itself never is.

    :param user: Node owner (defense-in-depth scoping).
    :param node_id: The UUID of the node to find ancestors for.
    :param stop_at: Optional subtree boundary (e.g. a share root UUID).
    :return: List of ancestor FsNode objects (only ``id``/``name`` are loaded),
             or None when ``stop_at`` is not on the parent chain, which means
             the node lies outside the allowed subtree.
    :raises FsNode.DoesNotExist: If the node does not exist or is not active.
    """
    cte = CTE.recursive(partial(
        make_fs_node_ancestor_cte,
        base_queryset=FsNode.active.filter(owner=user),
        node_id=node_id,
    ))
    rows = list(with_cte(cte, select=cte.queryset().values('id', 'parent_id', 'depth')))
    if not rows:
        raise FsNode.DoesNotExist

    # depth 0 is the node itself, the largest depth is the topmost ancestor.
    ids = [row['id'] for row in sorted(rows, key=lambda row: row['depth'], reverse=True)]

    if stop_at is not None:
        if stop_at not in ids:
            # The node is not a descendant of the allowed subtree root.
            return None
        ids = ids[ids.index(stop_at):]

    # Drop the node itself.
    ancestor_ids = ids[:-1]
    if not ancestor_ids:
        return []

    by_id = {
        node.id: node
        # The chain was resolved from the active manager; filter again so a
        # node that left the active state mid-walk cannot leak into the result.
        for node in FsNode.active.filter(id__in=ancestor_ids).only('id', 'name')
    }
    return [by_id[ancestor_id] for ancestor_id in ancestor_ids]


def get_fs_node_by_id(
        user: AbstractBaseUser,
        node_id: uuid.UUID,
) -> tuple[FsNode, list[FsNode]]:
    """
    Retrieve an active FsNode owned by the user by its UUID, with its ancestors.

    :param user: Node owner (owner-scope is mandatory, lookups are IDOR-safe).
    :param node_id: The UUID of the node.
    :return: A tuple of the node and its ancestors (root first).
    :raises FsNode.DoesNotExist: If the node is missing, foreign or tombstoned.
    """
    node: FsNode = FsNode.active.get(id=node_id, owner=user)
    return node, get_fs_node_ancestors(user, node.pk)
