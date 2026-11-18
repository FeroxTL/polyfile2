import hashlib
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

import magic
import marshmallow
from django.core.files import File
from django.db import IntegrityError, models, transaction
from django.db.models import Q
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


class DeletionMode:
    """Marking modes for :func:`mark_subtree_for_deletion`."""
    PERMANENT = "permanent"
    PURGE = "purge"


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


def _fs_node_exists_error(existing: FsNode) -> exceptions.FsNodeExistsError:
    """Build the API error describing an active sibling with the same name."""
    existing_kind = "Directory" if existing.is_directory else "File"
    return exceptions.FsNodeExistsError(
        detail=f'{existing_kind} named "{existing.name}" already exists',
        extra={
            "existing_node_id": str(existing.pk),
            "existing_type": existing.type,
        },
    )


def _get_active_sibling(
        user: User,
        fs_node: FsNode,
        name: str,
) -> FsNode | None:
    """Return an active sibling of ``fs_node`` with ``name``, if any."""
    return (
        FsNode.active.filter(
            owner=user,
            storage_id=fs_node.storage_id,
            parent_id=fs_node.parent_id,
            name=name,
        )
        .exclude(pk=fs_node.pk)
        .first()
    )


def create_fs_node(
        user: User,
        parent_id: uuid.UUID | None,
        name: str,
        fs_node_type: FsNode.TypeChoices,
        replace: bool = False,
) -> FsNode:
    """
    Create FsNode by parent UUID and name.

    :param user: FSNode owner.
    :param parent_id: target directory UUID; None means the virtual root.
    :param name: new node name (no path separators).
    :param fs_node_type: type of FSNode to be created.
    :param replace: reuse an existing file node with the same name instead of
        raising a conflict. Directories can never be replaced.
    :raises HttpException: most of the errors.
    :return: created or reused FSNode.
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
        if replace and fs_node_type == FsNode.TypeChoices.FILE and fs_node.is_file:
            return fs_node

        raise _fs_node_exists_error(fs_node)
    return fs_node


def rename_fs_node(
        user: User,
        node_id: uuid.UUID,
        name: str,
) -> FsNode:
    """
    Rename an active FsNode (file/directory) without moving it.

    Only the leaf name changes: the UUID, parent, share links and the
    physical object key stay intact. The name is validated with the same
    rules as :func:`create_fs_node`, and an active sibling with the same
    name is rejected with ``FsNodeExistsError``.

    :param user: FsNode owner.
    :param node_id: UUID of the node to rename.
    :param name: new leaf name.
    :raises HttpException: most of the errors.
    :return: renamed FsNode.
    """
    try:
        get_fs_node_name_validator()(name)
    except marshmallow.ValidationError as e:
        raise exceptions.InvalidFsNodeName(detail=', '.join(e.messages))

    try:
        fs_node = FsNode.active.get(id=node_id, owner=user)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access node "{node_id}" - no such file or directory',
        )

    if fs_node.name == name:
        return fs_node

    previous_name = fs_node.name
    fs_node.name = name
    try:
        # The savepoint keeps a caught IntegrityError from poisoning an outer
        # transaction (Django tests wrap each test in one) and lets the
        # conflict lookup run afterwards.
        with transaction.atomic():
            fs_node.save(update_fields=("name",))
    except IntegrityError as exc:
        # The partial unique constraint is the final guard: a concurrent
        # create/rename may have created the sibling after our lookup.
        fs_node.name = previous_name
        conflict = _get_active_sibling(user=user, fs_node=fs_node, name=name)
        if conflict is not None:
            raise _fs_node_exists_error(conflict) from exc
        raise

    return fs_node


def mark_subtree_for_deletion(
        user: User,
        fs_node: FsNode,
        deletion_mode: str,
) -> FsNodeDeletionJob:
    """
    Tombstone the subtree of ``fs_node`` and schedule its physical removal.

    Single marking algorithm shared by permanent deletion (from the file
    manager) and trash purging:

    - ``protected`` nodes survive: already tombstoned (``deleted_at``),
      retained scaffolding (``trash_retained_at``) and trash entries of a
      foreign batch (permanent mode: any trashed node).
    - Their ancestors inside the subtree become retained scaffolding
      (``trash_retained_at``) and lose their trash flags.
    - Everything else is tombstoned (``deleted_at`` + ``deletion_job``).

    :param user: Subtree owner.
    :param fs_node: Subtree root: an active node for permanent deletion or a
        trash entry root for purging.
    :param deletion_mode: ``permanent`` or ``purge``.
    :return: The created ``FsNodeDeletionJob``.
    :raises ValueError: On an unknown deletion mode.
    :raises FsNode.DoesNotExist: If the root no longer matches the mode's state.
    """
    if deletion_mode not in (DeletionMode.PERMANENT, DeletionMode.PURGE):
        raise ValueError(f"Unknown deletion mode: {deletion_mode}")

    with transaction.atomic():
        job = FsNodeDeletionJob.objects.create(
            owner=user,
            root_node_uuid=fs_node.pk,
            root_node_name=fs_node.name,
            status=FsNodeDeletionJob.Status.PENDING,
        )

        if deletion_mode == DeletionMode.PERMANENT:
            anchor = FsNode.active.filter(pk=fs_node.pk, owner=user)
        else:
            anchor = FsNode.trash.filter(pk=fs_node.pk, owner=user)
        if not anchor.exists():
            # The root was changed concurrently (trashed, purged or restored).
            raise FsNode.DoesNotExist(
                f'Node "{fs_node.pk}" no longer matches the "{deletion_mode}" deletion mode'
            )

        # Get all descendants via CTE-like approach using recursion.
        cte = CTE.recursive(
            lambda cte: FsNode.objects.filter(pk=fs_node.pk, owner=user)
            .values("pk", "parent_id")
            .union(
                cte.join(FsNode, parent_id=cte.col.pk).values("pk", "parent_id"),
                all=True,
            )
        )
        rows = with_cte(cte, select=cte.join(FsNode, pk=cte.col.pk).values("pk", "parent_id"))
        subtree_ids = [row["pk"] for row in rows]
        parent_of = {row["pk"]: row["parent_id"] for row in rows}

        if subtree_ids:
            subtree = FsNode.objects.filter(pk__in=subtree_ids)
            protected_filter = Q(deleted_at__isnull=False) | Q(trash_retained_at__isnull=False)
            if deletion_mode == DeletionMode.PERMANENT:
                protected_filter |= Q(trashed_at__isnull=False)
            else:
                protected_filter |= Q(trashed_at__isnull=False) & ~Q(trash_batch_id=fs_node.trash_batch_id)

            protected_ids = set(
                subtree.filter(protected_filter).values_list("pk", flat=True)
            )
            # Ancestors of protected nodes inside the subtree become retained
            # scaffolding. The parent map only contains subtree rows, so the
            # walk naturally stops at the subtree root.
            ancestors: set = set()
            for protected_id in protected_ids:
                current = parent_of.get(protected_id)
                while current is not None and current in parent_of:
                    ancestors.add(current)
                    current = parent_of[current]
            retained_ids = ancestors - protected_ids
            doomed_ids = set(subtree_ids) - protected_ids - ancestors

            if retained_ids:
                # Retained scaffolding must never keep trash flags: a purged
                # entry disappears from the trash immediately and un-revealing
                # it later yields a plain active (empty) directory.
                FsNode.objects.filter(pk__in=retained_ids).update(
                    trash_retained_at=now(),
                    trashed_at=None,
                    trash_batch_id=None,
                    trash_purge_after=None,
                )

            if doomed_ids:
                FsNode.objects.filter(pk__in=doomed_ids).update(
                    deleted_at=now(),
                    deletion_job=job,
                )

            # A deleted root invalidates its archive: release the manifest
            # before tombstoning the nodes so the deletion worker can proceed.
            cancel_archive_jobs_for_subtree(subtree_ids)
            # Revoke shares
            SharedNode.objects.filter(root_fs_node_id__in=subtree_ids, revoked_at__isnull=True).update(
                revoked_at=now(),
            )
            # Cancel temp uploads
            TempUpload.objects.filter(fs_node_id__in=subtree_ids).delete()

        job.total_nodes = len(doomed_ids)
        job.save(update_fields=("total_nodes",))
        return job


def remove_fs_node(user: User, node_id: uuid.UUID) -> FsNodeDeletionJob:
    """
    Permanently remove FsNode (file/directory) by its UUID.

    Uses asynchronous deletion: marks subtree as deleted (tombstone) and schedules
    a background job for physical removal. Trashed nodes survive (trash entries
    are protected; their ancestors become retained scaffolding).
    """
    try:
        fs_node = FsNode.active.get(id=node_id, owner=user)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access node "{node_id}" - no such file or directory',
        )

    try:
        return mark_subtree_for_deletion(user, fs_node, deletion_mode=DeletionMode.PERMANENT)
    except FsNode.DoesNotExist as exc:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access node "{node_id}" - no such file or directory',
        ) from exc
