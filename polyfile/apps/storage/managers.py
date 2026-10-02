from functools import partial
from pathlib import PurePosixPath

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models.functions import Concat
from django_cte import CTE, with_cte

from polyfile.apps.storage.models import FsNode


def make_fs_node_cte(cte: CTE, base_queryset: models.QuerySet, parent_fs_node: FsNode | None) -> models.QuerySet:
    """
    Construct a recursive Common Table Expression (CTE) for FsNode.

    This function builds the base and recursive parts of the CTE. If `parent_fs_node` 
    is provided, it restricts the starting set of nodes to the immediate children of 
    that parent. Otherwise, it starts from the root nodes (nodes with no parent).

    :param cte: The CTE object.
    :param base_queryset: The QuerySet of FsNode objects to filter.
    :param parent_fs_node: Optional parent FsNode. If set, only its children
                             will be used as the root of the recursive expansion.
    """
    # non-recursive: get root nodes
    qs = base_queryset
    if parent_fs_node:
        qs = qs.filter(parent=parent_fs_node)
    else:
        qs = qs.filter(parent__isnull=True)

    return qs.values(
        'id',
        path=Concat(models.Value('/'), models.F('name')),
    ).union(
        # recursive union: get descendants
        cte.join(base_queryset.model, parent_id=cte.col.id).values(
            'id',
            path=Concat(
                cte.col.path, models.Value('/'), models.F('name'),
                output_field=models.TextField(),
            ),
        ),
        all=False,
    )


def get_user_fs_node_by_path(
        user: AbstractBaseUser,
        path: PurePosixPath,
        parent_fs_node: FsNode | None = None,
) -> FsNode | None:
    """
    Retrieve an FsNode for a specific user and path.

    If `parent_fs_node` is provided, the search is restricted to the subtree 
    of that parent node. The `path` argument should be relative to the 
    parent's path in this context.

    :param user: The AbstractBaseUser instance of the FsNode owner.
    :param path: The PurePosixPath to search for.
    :param parent_fs_node: Optional FsNode. If provided, restricts the 
                             search to its descendants.
    :return: The FsNode instance if found, otherwise None (for root path).
    :raises FsNode.DoesNotExist: If no matching node is found in the subtree.
    """
    if path == PurePosixPath('/'):
        if parent_fs_node is not None:
            parent_fs_node.path = str(path / parent_fs_node.name)
        return parent_fs_node

    cte = CTE.recursive(partial(
        make_fs_node_cte,
        base_queryset=FsNode.objects.filter(owner=user),
        parent_fs_node=parent_fs_node,
    ))
    return with_cte(
        cte,
        select=cte.join(FsNode, id=cte.col.id)
        .annotate(path=cte.col.path)
        .filter(path=path, owner=user)
    ).get()
