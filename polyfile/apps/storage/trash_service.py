"""Trash (recycle bin) services.

Trash state lives on ``FsNode`` (``trashed_at`` / ``trash_batch_id`` /
``trash_purge_after`` / ``trash_retained_at``); see the trash feature plan for
the state model and invariants. This module implements:

- ``trash_fs_node``: move a node (and its active subtree) to the trash.
- ``restore_fs_node``: restore a trash entry, resolving hidden scaffolding
  and trashed ancestors on the way.
- ``purge_trash_entry`` / ``empty_trash``: permanent removal of trash entries
  (nested trash entries survive and stay visible).
- ``enqueue_expired_trash_purges``: TTL sweep (creates deletion jobs).
- ``reap_trash_scaffolding``: remove retained directories that no longer
  protect anything.
"""

import uuid
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import models, transaction
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError
from django.utils.timezone import now
from django_cte import CTE, with_cte

from polyfile.apps.accounts.models import User
from polyfile.apps.share.models import SharedNode
from polyfile.apps.storage.archive import cancel_archive_jobs_for_subtree
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob, TempUpload
from polyfile.apps.storage.schemas import (
    RESTORE_CONFLICT_CHOICES,
    RESTORE_CONFLICT_FAIL,
    RESTORE_CONFLICT_RENAME,
)
from polyfile.apps.storage.utils import DeletionMode, mark_subtree_for_deletion
from polyfile.core import exceptions

# "name (1000)" is the longest generated suffix: 7 characters.
_RENAME_MAX_BASE_LENGTH = 255 - len(" (1000)")
_RENAME_MAX_ATTEMPTS = 1000


@dataclass
class RestoreResult:
    """Outcome of :func:`restore_fs_node`."""
    node: FsNode
    # Trash entries restored implicitly (trashed ancestors of the target).
    restored_entries: list[FsNode] = field(default_factory=list)
    # Side effects on the way: merges and renames.
    notices: list[dict] = field(default_factory=list)


def get_trash_ttl() -> timedelta:
    """TTL for trash entries; purged automatically after it expires."""
    return timedelta(days=getattr(settings, "POLYFILE_TRASH_TTL_DAYS", 30))


def get_trash_root_filter() -> Q:
    """Filter selecting trash entry roots (visible entries, invariant I2)."""
    return Q(parent__isnull=True) | Q(parent__trashed_at__isnull=True) | ~Q(
        parent__trash_batch_id=F("trash_batch_id")
    )


def get_trash_roots(user: User | None = None):
    """Queryset of visible trash entry roots, newest first."""
    queryset = FsNode.trash.all()
    if user is not None:
        queryset = queryset.filter(owner=user)
    return queryset.filter(get_trash_root_filter()).order_by("-trashed_at")


def trash_fs_node(user: User, node_id: uuid.UUID) -> FsNode:
    """
    Move an FsNode (and its active subtree) to the trash.

    The subtree is marked with a fresh ``trash_batch_id``; nodes that are
    already trashed (nested entries) keep their own batch and TTL. Shares are
    revoked, temp uploads are cancelled and archive jobs are released.

    :raises HttpException: If the node is not an accessible active node.
    :return: The trashed root node.
    """
    try:
        fs_node = FsNode.active.get(id=node_id, owner=user)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access node "{node_id}" - no such file or directory',
        )

    trashed_time = now()
    batch_id = uuid.uuid4()
    with transaction.atomic():
        # Recurse over all objects: the subtree may contain nested trash
        # entries, which must keep their own batch and TTL.
        cte = _subtree_cte(fs_node, user)
        rows = with_cte(cte, select=cte.join(FsNode, pk=cte.col.pk).values("pk"))
        subtree_ids = [row["pk"] for row in rows]

        FsNode.objects.filter(
            pk__in=subtree_ids,
            trashed_at__isnull=True,
            trash_retained_at__isnull=True,
        ).update(
            trashed_at=trashed_time,
            trash_batch_id=batch_id,
            trash_purge_after=trashed_time + get_trash_ttl(),
        )
        # Revoke shares
        SharedNode.objects.filter(root_fs_node_id__in=subtree_ids, revoked_at__isnull=True).update(
            revoked_at=trashed_time,
        )
        # Cancel temp uploads
        TempUpload.objects.filter(fs_node_id__in=subtree_ids).delete()
        # Release archive manifests so a later purge is not blocked
        cancel_archive_jobs_for_subtree(subtree_ids)

    fs_node.refresh_from_db()
    return fs_node


def _subtree_cte(fs_node: FsNode, user: User):
    """Recursive CTE selecting ``fs_node`` and all its descendants."""
    return CTE.recursive(
        lambda cte: FsNode.objects.filter(pk=fs_node.pk, owner=user)
        .values("pk")
        .union(
            cte.join(FsNode, parent_id=cte.col.pk).values("pk"),
            all=True,
        )
    )


def _get_trash_entry(user: User, entry_id: uuid.UUID) -> FsNode:
    """Fetch a visible trash entry root owned by ``user``."""
    try:
        entry = FsNode.trash.get(id=entry_id, owner=user)
    except FsNode.DoesNotExist:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access trash entry "{entry_id}" - no such entry',
        )
    if not _is_trash_root(user, entry):
        # Only top-level entries can be restored or purged.
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access trash entry "{entry_id}" - no such entry',
        )
    return entry


def _is_trash_root(user: User, entry: FsNode) -> bool:
    """Invariant I2: the entry is not nested inside another trash entry."""
    if entry.parent_id is None:
        return True
    parent = FsNode.objects.filter(pk=entry.parent_id, owner=user).only(
        "trashed_at", "trash_batch_id", "trash_retained_at"
    ).first()
    if parent is None:
        # Defensive: a dangling parent cannot exist for a trashed node.
        return True
    return not parent.trashed_at or parent.trash_batch_id != entry.trash_batch_id


def restore_fs_node(
        user: User,
        entry_id: uuid.UUID,
        on_conflict: str = RESTORE_CONFLICT_FAIL,
) -> RestoreResult:
    """
    Restore a trash entry to its original location.

    The node stays attached to its parent, so it always lands on the exact
    path stored in the database. Hidden scaffolding on the way is un-hidden
    (merging into an active same-name directory when needed) and trashed
    ancestors are restored first (their entries are restored implicitly).

    :param user: Entry owner.
    :param entry_id: Trash entry root UUID.
    :param on_conflict: ``fail`` (409 on a name conflict) or ``rename``
        (restore as ``name (N)``).
    :raises HttpException: Unknown entry, unknown conflict mode or a name
        conflict in ``fail`` mode.
    :return: :class:`RestoreResult` with the restored node, the implicitly
        restored entries and the notices (merges/renames) collected on the way.
    """
    if on_conflict not in RESTORE_CONFLICT_CHOICES:
        raise exceptions.BadRequest(detail=f'Unknown on_conflict value: "{on_conflict}"')

    entry = _get_trash_entry(user, entry_id)

    restored_entries: list[FsNode] = []
    notices: list[dict] = []
    with transaction.atomic():
        _restore_entry(user, entry, on_conflict, restored_entries, notices)
    # The batch UPDATE happened in SQL; refresh every returned node.
    entry.refresh_from_db()
    for restored in restored_entries:
        restored.refresh_from_db()
    return RestoreResult(node=entry, restored_entries=restored_entries, notices=notices)


def _restore_entry(
        user: User,
        entry: FsNode,
        on_conflict: str,
        restored_entries: list[FsNode],
        notices: list[dict],
) -> None:
    """Restore one trash entry inside an active ancestor chain.

    The entry itself is not added to ``restored_entries``; only implicitly
    restored ancestors are reported there (by ``_ensure_ancestors_active``).
    """
    _ensure_ancestors_active(user, entry, restored_entries, notices)
    # A merge on the way may have re-parented the entry into another directory.
    entry.refresh_from_db()

    if FsNode.active.filter(parent_id=entry.parent_id, name=entry.name, owner=user).exists():
        if on_conflict == RESTORE_CONFLICT_RENAME:
            entry.name = _next_free_name(user, entry.parent_id, entry.name)
            entry.save(update_fields=("name",))
            notices.append({"type": "renamed", "name": entry.name})
        else:
            existing = FsNode.active.get(parent_id=entry.parent_id, name=entry.name, owner=user)
            raise exceptions.FsNodeExistsError(
                detail=f'{existing.get_type_display()} named "{existing.name}" already exists',
                extra={
                    "existing_node_id": str(existing.pk),
                    "existing_type": existing.type,
                },
            )

    FsNode.objects.filter(owner=user, trash_batch_id=entry.trash_batch_id).update(
        trashed_at=None,
        trash_batch_id=None,
        trash_purge_after=None,
    )


def _ensure_ancestors_active(
        user: User,
        node: FsNode,
        restored_entries: list[FsNode],
        notices: list[dict],
) -> None:
    """Make the whole parent chain of ``node`` active."""
    if node.parent_id is None:
        return
    parent = FsNode.objects.filter(pk=node.parent_id, owner=user).first()
    if parent is None:
        # Defensive: a dangling parent cannot exist for a trashed node.
        return
    if parent.trash_retained_at is not None:
        _unhide(user, parent, restored_entries, notices)
    elif parent.trashed_at is not None:
        batch_root = _find_batch_root(user, parent)
        # Implicit chain restores rename on conflict to keep the restore
        # seamless; the event is reported to the user.
        _restore_entry(user, batch_root, RESTORE_CONFLICT_RENAME, restored_entries, notices)
        restored_entries.append(batch_root)


def _unhide(
        user: User,
        retained: FsNode,
        restored_entries: list[FsNode],
        notices: list[dict],
) -> None:
    """
    Make a retained scaffolding directory visible again.

    The ancestors are resolved first: merging this node into an active
    same-name sibling must happen while its subtree is still retained or
    trashed (excluded from the unique constraints).

    If an active sibling with the same name exists, the scaffolding is merged
    into it (directories) or renamed (when the sibling is a file). Only the
    path of the restored entry is un-hidden.
    """
    _ensure_ancestors_active(user, retained, restored_entries, notices)
    # An ancestor merge may have re-parented this node.
    retained.refresh_from_db()

    conflict = FsNode.active.filter(
        parent_id=retained.parent_id, name=retained.name, owner=user
    ).first()
    if conflict is not None:
        if conflict.is_directory and retained.is_directory:
            # Merge: re-parent the retained subtree into the active directory
            # and drop the scaffolding row. Retained subtrees contain only
            # trashed/retained/tombstoned nodes, so no unique constraint can
            # be violated here.
            FsNode.objects.filter(parent_id=retained.pk).update(parent=conflict)
            # Queryset delete avoids FsNode.delete(), which would try to
            # remove a storage object (retained nodes are directories).
            try:
                FsNode.objects.filter(pk=retained.pk).delete()
            except ProtectedError as exc:
                raise exceptions.FsNodeExistsError(
                    detail=f'Can not merge "{retained.name}" - it is still referenced by an archive snapshot',
                ) from exc
            notices.append({"type": "merged", "name": conflict.name})
            # The merge target's chain is already active.
            return
        # A directory can not be merged into a file: rename instead.
        retained.name = _next_free_name(user, retained.parent_id, retained.name)
        notices.append({"type": "renamed", "name": retained.name})

    retained.trash_retained_at = None
    retained.save(update_fields=("trash_retained_at", "name"))


def _find_batch_root(user: User, node: FsNode) -> FsNode:
    """Topmost trashed node sharing ``node``'s trash batch."""
    current = node
    while current.parent_id is not None:
        parent = FsNode.objects.filter(pk=current.parent_id, owner=user).only(
            "trashed_at", "trash_batch_id"
        ).first()
        if parent is None or not parent.trashed_at or parent.trash_batch_id != current.trash_batch_id:
            break
        current = parent
    return current


def _next_free_name(user: User, parent_id: uuid.UUID | None, base_name: str) -> str:
    """First free ``base (N)`` name among the active siblings."""
    base = base_name[:_RENAME_MAX_BASE_LENGTH]
    taken = set(
        FsNode.active.filter(parent_id=parent_id, owner=user)
        .filter(name__startswith=f"{base} (")
        .values_list("name", flat=True)
    )
    if base_name != base and base_name in taken:
        taken.discard(base_name)
    for attempt in range(1, _RENAME_MAX_ATTEMPTS + 1):
        candidate = f"{base} ({attempt})"
        if candidate not in taken:
            return candidate
    raise exceptions.FsNodeExistsError(
        detail=f'Can not find a free name for "{base_name}"',
    )


def purge_trash_entry(user: User, entry_id: uuid.UUID) -> FsNodeDeletionJob:
    """
    Permanently remove a trash entry.

    The entry's own batch is tombstoned and physically removed by the worker.
    Nested trash entries (foreign batches) survive and stay visible; their
    ancestors inside the subtree (including the entry root itself) become
    retained scaffolding.

    :raises HttpException: Unknown entry.
    """
    entry = _get_trash_entry(user, entry_id)
    try:
        return mark_subtree_for_deletion(user, entry, deletion_mode=DeletionMode.PURGE)
    except FsNode.DoesNotExist as exc:
        raise exceptions.FsNodeNotFoundError(
            detail=f'Can not access trash entry "{entry_id}" - no such entry',
        ) from exc


def empty_trash(user: User) -> list[FsNodeDeletionJob]:
    """
    Purge every visible trash entry of the user.

    Creates one deletion job per entry. Entries nested inside other entries
    are protected by the marking algorithm and are handled by their own jobs;
    the reaper cleans up the scaffolding afterwards.
    """
    jobs: list[FsNodeDeletionJob] = []
    # Materialize the entry list first: purging mutates the structure.
    entry_ids = list(get_trash_roots(user).values_list("pk", flat=True))
    for entry_id in entry_ids:
        try:
            entry = FsNode.trash.get(pk=entry_id, owner=user)
        except FsNode.DoesNotExist:
            continue
        try:
            jobs.append(mark_subtree_for_deletion(user, entry, deletion_mode=DeletionMode.PURGE))
        except FsNode.DoesNotExist:
            # Already tombstoned by a previous job of this operation.
            continue
    return jobs


def enqueue_expired_trash_purges(current_time=None) -> int:
    """
    Create purge jobs for trash entries whose TTL has expired.

    Runs periodically (deletion worker sweep or the ``purge_expired_trash``
    command). Nested entries are protected by the marking algorithm and
    expire on their own schedule.

    :return: Number of created deletion jobs.
    """
    current_time = current_time or now()
    created = 0
    expired = get_trash_roots().filter(trash_purge_after__lte=current_time)
    for entry_id in list(expired.values_list("pk", flat=True)):
        try:
            entry = FsNode.trash.get(pk=entry_id)
        except FsNode.DoesNotExist:
            continue
        try:
            mark_subtree_for_deletion(entry.owner, entry, deletion_mode=DeletionMode.PURGE)
        except FsNode.DoesNotExist:
            # Already tombstoned by a concurrent sweep or a nested purge.
            continue
        created += 1
    return created


def reap_trash_scaffolding(batch_size: int = 500) -> int:
    """
    Delete retained directories that no longer protect anything.

    A retained directory with no children is garbage scaffolding: its trashed
    descendants were restored or purged. Repeated passes clean multi-level
    chains bottom-up. Safe against races: while a trashed or tombstoned
    descendant exists, the directory is not childless.

    :return: Number of removed rows.
    """
    total = 0
    while True:
        retained_ids = list(
            FsNode.objects.filter(
                trash_retained_at__isnull=False,
                type=FsNode.TypeChoices.DIRECTORY,
            )
            .annotate(
                has_children=models.Exists(
                    FsNode.objects.filter(parent_id=models.OuterRef("pk"))
                )
            )
            .filter(has_children=False)
            .order_by("pk")
            .values_list("pk", flat=True)[:batch_size]
        )
        if not retained_ids:
            break
        deleted_in_pass = 0
        try:
            deleted, _ = FsNode.objects.filter(pk__in=retained_ids).delete()
            deleted_in_pass = deleted
            total += deleted
        except ProtectedError:
            # An archive manifest still references one of the rows; delete
            # the unprotected ones one by one and retry the rest later.
            for retained_id in retained_ids:
                try:
                    deleted, _ = FsNode.objects.filter(pk=retained_id).delete()
                    deleted_in_pass += deleted
                    total += deleted
                except ProtectedError:
                    continue
        if deleted_in_pass == 0:
            # Every candidate is protected; further passes would loop forever.
            break
    return total
