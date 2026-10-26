import hashlib
import logging
import pathlib
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
from polyfile.apps.storage.managers import get_user_fs_node_by_path
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
        fs_node: FsNode | None = get_user_fs_node_by_path(user=user, path=path, parent_fs_node=parent_fs_node)
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
        fs_node.path = '/'
        # Return all root nodes
        fs_node_children = FsNode.active.filter(owner=user, parent__isnull=True)
    elif fs_node.is_file:
        # File node can not have child nodes, so make them empty
        fs_node_children = FsNode.active.none()
    else:
        assert fs_node.is_directory
        fs_node_children = FsNode.active.filter(owner=user, parent=fs_node)

    fs_node_children = fs_node_children.select_related("share").annotate(
        sort_priority=models.Case(
            # Directories go first
            models.When(type=FsNode.TypeChoices.DIRECTORY, then=models.Value(1)),
            default=models.Value(2),
            output_field=models.IntegerField()
        ),
    ).order_by('sort_priority', 'name')

    return FsNodeWithChildren(
        current=fs_node,
        children=fs_node_children,
    )


def create_fs_node(
        user: User,
        path: PurePosixPath,
        fs_node_type: FsNode.TypeChoices,
) -> FsNode:
    """
    Create FsNode.

    :param user: FSNode owner.
    :param path: target path with FSNode name included.
    :param fs_node_type: type of FSNode to be created.
    :raises HttpException: most of the errors.
    :return: created FSNode.
    """
    assert user.storage_id is not None
    base_qs: models.QuerySet[FsNode]
    parent_fs_node: FsNode | None
    parent_path = path.parent

    try:
        get_fs_node_name_validator()(path.name)
    except marshmallow.ValidationError as e:
        raise exceptions.InvalidFsNodeName(detail=', '.join(e.messages))

    if parent_path == PurePosixPath('/'):
        base_qs, parent_fs_node = FsNode.active.all(), None
    else:
        base_qs = FsNode.active.filter(parent__type=FsNode.TypeChoices.DIRECTORY)
        try:
            parent_fs_node = get_user_fs_node_by_path(user=user, path=parent_path)
        except FsNode.DoesNotExist:
            raise exceptions.FsNodeIsNotADirectoryError(detail=f'Directory "{parent_path}" does not exist')
        if not parent_fs_node.is_directory:
            raise exceptions.FsNodeIsNotADirectoryError(detail=f'"{parent_path}" is not a directory')

    fs_node, created = base_qs.get_or_create(
        name=path.name,
        owner=user,
        parent=parent_fs_node,
        defaults={
            'type': fs_node_type,
            'storage_id': user.storage_id,
        },
    )
    if not created:
        raise exceptions.FsNodeExistsError(
            detail=f'{fs_node_type.name.capitalize()} named "{path.name}" already exists')
    return fs_node


def remove_fs_node(user: User, path: pathlib.PurePosixPath) -> FsNodeDeletionJob:
    """
    Remove FsNode (file/directory) by path.

    Uses asynchronous deletion: marks subtree as deleted (tombstone) and schedules
    a background job for physical removal.
    """
    try:
        fs_node: FsNode | None = get_user_fs_node_by_path(user=user, path=path)
        if fs_node is None:
            raise FsNode.DoesNotExist
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access "{path}" - no such file or directory',
        )

    with transaction.atomic():
        job = FsNodeDeletionJob.objects.create(
            owner=user,
            root_path=str(path),
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
