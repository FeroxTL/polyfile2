import hashlib
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

import magic
import marshmallow
from django.core.files import File
from django.db import models, transaction
from django.utils.timezone import now
from django_cte import CTE, with_cte

from polyfile.apps.accounts.models import User
from polyfile.apps.share.models import SharedNode
from polyfile.apps.storage.archive import cancel_archive_jobs_for_subtree
from polyfile.apps.storage.managers import (
    get_fs_node_ancestors,
    get_fs_node_by_path_name,
)
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob, TempUpload
from polyfile.apps.storage.schemas import get_fs_node_name_validator
from polyfile.core import exceptions

logger = logging.getLogger(__name__)


def get_md5_sum(file: File) -> str:
    """Get md5 hash of file."""
    hash_md5 = hashlib.md5()
    file.seek(0)
    for chunk in iter(lambda: file.read(4096), b""):
        hash_md5.update(chunk)
    return hash_md5.hexdigest()


# noinspection PyBroadException
def get_mime_type(file: File) -> str:
    """Get mimetype of file."""
    file.seek(0)
    try:
        return magic.from_buffer(file.read(2048), mime=True)
    except Exception:
        logger.exception("Failed to determine the file's MIME type via 'magic'.")
        return ""


@dataclass
class FsNodeWithChildren:
    current: FsNode | None
    children: Iterable[FsNode]
    ancestors: Iterable[FsNode] = ()


def _sorted_fs_node_children(children: models.QuerySet) -> models.QuerySet:
    """Apply the default listing order: directories first, then by name."""
    return children.select_related("share").annotate(
        sort_priority=models.Case(
            # Directories go first
            models.When(type=FsNode.TypeChoices.DIRECTORY, then=models.Value(1)),
            default=models.Value(2),
            output_field=models.IntegerField()
        ),
    ).order_by('sort_priority', 'name')


def get_fs_node_with_children(
        user: User,
        path: PurePosixPath,
        parent_fs_node: FsNode | None = None,
) -> FsNodeWithChildren:
    """
    Retrieve FsNode (file/directory) by path and its children (if any).

    :param user: directory owner.
    :param path: listed path.
    :param parent_fs_node: parent node.
    :raises HttpException: most of the errors.
    :return FsNodeWithChildren: current FsNode and child FsNodes.
    """
    try:
        fs_node: FsNode | None = get_fs_node_by_path_name(user=user, path=path, parent_fs_node=parent_fs_node)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access "{path}" - no such file or directory',
        )

    if fs_node is None:
        # Make fs_node fake root user directory
        fs_node = FsNode(
            name='',
            type=FsNode.TypeChoices.DIRECTORY,
            storage=None,
            storage_id=None,
            owner=user,
            created_at=user.date_joined,
            modified_at=user.date_joined,
        )
        # The virtual root has no identity: it does not exist in the database.
        fs_node.pk = None
        ancestors: Iterable[FsNode] = []
        # Return all root nodes
        fs_node_children = FsNode.active.filter(owner=user, parent__isnull=True)
    else:
        stop_at = parent_fs_node.pk if parent_fs_node is not None else None
        ancestors = get_fs_node_ancestors(user=user, node_id=fs_node.pk, stop_at=stop_at)
        if ancestors is None:
            # The node is not a descendant of the allowed subtree root.
            raise exceptions.FsNodeNotFoundError(
                detail=f'Can not access "{path}" - no such file or directory',
            )

        if stop_at is not None and fs_node.pk == stop_at:
            # Never leak the share root's parent identity through the public API.
            fs_node.parent_id = None

        if fs_node.is_file:
            # File node can not have child nodes, so make them empty
            fs_node_children = FsNode.active.none()
        else:
            assert fs_node.is_directory
            fs_node_children = FsNode.active.filter(owner=user, parent=fs_node)

    return FsNodeWithChildren(
        current=fs_node,
        children=_sorted_fs_node_children(fs_node_children),
        ancestors=ancestors,
    )


def get_fs_node_with_children_by_id(
        user: User,
        node_id: uuid.UUID | None = None,
) -> FsNodeWithChildren:
    """
    Retrieve FsNode (file/directory) by its UUID and its children (if any).

    :param user: directory owner.
    :param node_id: target node UUID; None means the virtual root.
    :raises HttpException: most of the errors.
    :return FsNodeWithChildren: current FsNode, ancestors and child FsNodes.
    """
    if node_id is None:
        return get_fs_node_with_children(user=user, path=PurePosixPath("/"))

    try:
        fs_node = FsNode.active.get(id=node_id, owner=user)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access node "{node_id}" - no such file or directory',
        )

    ancestors = get_fs_node_ancestors(user=user, node_id=fs_node.pk)

    if fs_node.is_file:
        fs_node_children = FsNode.active.none()
    else:
        fs_node_children = FsNode.active.filter(owner=user, parent=fs_node)

    return FsNodeWithChildren(
        current=fs_node,
        children=_sorted_fs_node_children(fs_node_children),
        ancestors=ancestors,
    )


def create_fs_node(
        user: User,
        parent_id: uuid.UUID | None,
        name: str,
        fs_node_type: FsNode.TypeChoices,
) -> FsNode:
    """
    Create FsNode by parent UUID and name.

    :param user: FSNode owner.
    :param parent_id: target directory UUID; None means the virtual root.
    :param name: new node name (no path separators).
    :param fs_node_type: type of FSNode to be created.
    :raises HttpException: most of the errors.
    :return: created FSNode.
    """
    assert user.storage_id is not None

    try:
        get_fs_node_name_validator()(name)
    except marshmallow.ValidationError as e:
        raise exceptions.InvalidFsNodeName(detail=', '.join(e.messages))

    if parent_id is None:
        parent_fs_node = None
    else:
        try:
            parent_fs_node = FsNode.active.get(id=parent_id, owner=user)
        except FsNode.DoesNotExist:
            raise exceptions.FsNodeNotFoundError(
                detail=f'Can not access node "{parent_id}" - no such file or directory',
            )
        if not parent_fs_node.is_directory:
            raise exceptions.FsNodeIsNotADirectoryError(
                detail=f'"{parent_fs_node.name}" is not a directory',
            )

    fs_node, created = FsNode.active.get_or_create(
        name=name,
        owner=user,
        parent=parent_fs_node,
        defaults={
            'type': fs_node_type,
            'storage_id': user.storage_id,
        },
    )
    if not created:
        raise exceptions.FsNodeExistsError(
            detail=f'{fs_node_type.name.capitalize()} named "{name}" already exists')
    return fs_node


def _remove_fs_node(user: User, fs_node: FsNode) -> FsNodeDeletionJob:
    """
    Tombstone the node subtree and schedule its physical removal.

    Uses asynchronous deletion: marks subtree as deleted (tombstone) and schedules
    a background job for physical removal.
    """
    with transaction.atomic():
        job = FsNodeDeletionJob.objects.create(
            owner=user,
            root_node_uuid=fs_node.pk,
            root_node_name=fs_node.name,
            status=FsNodeDeletionJob.Status.PENDING,
        )

        # Get all descendants via CTE-like approach using recursion
        cte = CTE.recursive(
            lambda cte: FsNode.active.filter(pk=fs_node.pk, owner=user, deleted_at__isnull=True)
            .values("pk")
            .union(
                cte.join(FsNode, parent_id=cte.col.pk).values("pk"),
                all=True,
            )
        )
        rows = with_cte(cte, select=cte.join(FsNode, pk=cte.col.pk).values("pk"))
        subtree_ids = [row["pk"] for row in rows]

        if subtree_ids:
            # A deleted root invalidates its archive: release the manifest
            # before tombstoning the nodes so the deletion worker can proceed.
            cancel_archive_jobs_for_subtree(subtree_ids)
            FsNode.objects.filter(pk__in=subtree_ids).update(
                deleted_at=now(),
                deletion_job=job,
            )
            # Revoke shares
            SharedNode.objects.filter(root_fs_node_id__in=subtree_ids, revoked_at__isnull=True).update(
                revoked_at=now(),
            )
            # Cancel temp uploads
            TempUpload.objects.filter(fs_node_id__in=subtree_ids).delete()

        job.total_nodes = len(subtree_ids)
        job.save(update_fields=("total_nodes",))
        return job


def remove_fs_node(user: User, node_id: uuid.UUID) -> FsNodeDeletionJob:
    """
    Remove FsNode (file/directory) by its UUID.

    Uses asynchronous deletion: marks subtree as deleted (tombstone) and schedules
    a background job for physical removal.
    """
    try:
        fs_node = FsNode.active.get(id=node_id, owner=user)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access node "{node_id}" - no such file or directory',
        )

    return _remove_fs_node(user, fs_node)
