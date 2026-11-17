"""Directory archive snapshot service.

A directory archive is built from an immutable manifest
(:class:`~polyfile.apps.storage.models.FsNodeArchiveItem`), not from the live
tree. The manifest stores the metadata and ZIP path of every entry at request
time, and its ``node`` foreign key uses ``PROTECT`` so the deletion worker
cannot physically remove a snapshotted node until the archive job reaches a
terminal state.
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils.timezone import now
from django_cte import CTE, with_cte

from polyfile.apps.accounts.models import User
from polyfile.apps.storage.models import FsNode, FsNodeArchiveItem, FsNodeArchiveJob
from polyfile.apps.storage.services import has_download_access
from polyfile.apps.storage.storage_objects import StorageObjectRef
from polyfile.core import exceptions

if TYPE_CHECKING:
    from polyfile.apps.share.models import SharedNode


DEFAULT_MAX_FILES = 10_000
DEFAULT_MAX_SIZE = 10 * 1024 ** 3
MAX_ZIP_PATH_LENGTH = 1024


@dataclass(frozen=True)
class ManifestEntry:
    """One immutable entry of a directory snapshot."""

    node_id: uuid.UUID | None
    entry_type: str
    zip_path: str
    storage_object: StorageObjectRef | None
    size: int
    md5: str
    modified_at: datetime | None


def _load_subtree(root: FsNode) -> list[dict]:
    """Load the active subtree of ``root`` in a single recursive CTE.

    Trashed nodes (recycle bin) and retained scaffolding are excluded: they
    are invisible in the file manager and must not leak into an archive.
    """
    active_children = Q(
        deleted_at__isnull=True,
        trashed_at__isnull=True,
        trash_retained_at__isnull=True,
    )
    cte = CTE.recursive(
        lambda cte: FsNode.active.filter(pk=root.pk)
        .values("pk")
        .union(
            cte.join(FsNode, parent_id=cte.col.pk)
            .filter(active_children)
            .values("pk"),
            all=True,
        )
    )
    return list(
        with_cte(
            cte,
            select=cte.join(FsNode, pk=cte.col.pk)
            .filter(active_children)
            .values(
                "pk",
                "parent_id",
                "name",
                "type",
                "object_key",
                "storage_id",
                "size",
                "md5",
                "modified_at",
            ),
        )
    )


def _validate_name(name: str) -> None:
    if not name or name in (".", ".."):
        raise exceptions.InvalidFsNodeName(
            detail=f'Cannot archive invalid name "{name}".'
        )
    if "/" in name or "\\" in name or "\x00" in name:
        raise exceptions.InvalidFsNodeName(
            detail=f'Cannot archive name "{name}": path separators are not allowed.'
        )


def _validate_zip_path(zip_path: str) -> None:
    if len(zip_path) > MAX_ZIP_PATH_LENGTH:
        raise exceptions.ArchiveLimitExceeded(
            detail=(
                f'Archive path is longer than {MAX_ZIP_PATH_LENGTH} characters: '
                f'"{zip_path[:80]}...".'
            )
        )


def build_manifest_entries(rows: list[dict], root: FsNode) -> list[ManifestEntry]:
    """Build deterministic ZIP entries from a subtree snapshot.

    The root itself is not included: the archive contains the directory
    contents and is downloaded as ``<root_node_name>.zip``. Directory entries
    end with ``/`` so empty directories survive the round-trip.
    """
    children_by_parent: dict[uuid.UUID, list[dict]] = {}
    for row in rows:
        if row["pk"] == root.pk:
            continue
        children_by_parent.setdefault(row["parent_id"], []).append(row)

    entries: list[ManifestEntry] = []
    stack: list[tuple[uuid.UUID, str]] = [(root.pk, "")]
    while stack:
        parent_id, prefix = stack.pop()
        children = sorted(
            children_by_parent.get(parent_id, []),
            key=lambda row: row["name"],
        )
        for row in children:
            _validate_name(row["name"])
            is_directory = row["type"] == FsNode.TypeChoices.DIRECTORY
            zip_path = f"{prefix}{row['name']}/" if is_directory else f"{prefix}{row['name']}"
            _validate_zip_path(zip_path)
            storage_object = None
            if not is_directory and row["object_key"]:
                storage_object = StorageObjectRef(row["storage_id"], row["object_key"])
            entries.append(
                ManifestEntry(
                    node_id=None if is_directory else row["pk"],
                    entry_type=(
                        FsNodeArchiveItem.EntryType.DIRECTORY
                        if is_directory
                        else FsNodeArchiveItem.EntryType.FILE
                    ),
                    zip_path=zip_path,
                    storage_object=storage_object,
                    size=0 if is_directory else row["size"],
                    md5="" if is_directory else (row["md5"] or ""),
                    modified_at=row["modified_at"],
                )
            )
            if is_directory:
                stack.append((row["pk"], zip_path))

    entries.sort(key=lambda entry: entry.zip_path)
    return entries


def compute_fingerprint(rows: list[dict]) -> str:
    """Return a stable fingerprint of the subtree metadata.

    It changes when files are added, removed, resized or modified. Rename and
    move keep the same fingerprint on purpose: the existing snapshot is still a
    valid archive of the same tree.
    """
    total_bytes = sum(row["size"] for row in rows)
    latest_modified = max(
        (row["modified_at"] for row in rows if row["modified_at"] is not None),
        default=None,
    )
    payload = "{}:{}:{}".format(
        len(rows),
        total_bytes,
        latest_modified.isoformat() if latest_modified is not None else "",
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _check_limits(total_files: int, total_bytes: int) -> None:
    max_files = getattr(settings, "DIRECTORY_ARCHIVE_MAX_FILES", DEFAULT_MAX_FILES)
    max_size = getattr(settings, "DIRECTORY_ARCHIVE_MAX_SIZE", DEFAULT_MAX_SIZE)

    if total_files > max_files:
        raise exceptions.ArchiveLimitExceeded(
            detail=(
                f"Directory contains {total_files} files; "
                f"the archive limit is {max_files}."
            )
        )
    if total_bytes > max_size:
        raise exceptions.ArchiveLimitExceeded(
            detail=(
                f"Directory contains {total_bytes} bytes; "
                f"the archive limit is {max_size}."
            )
        )


def _check_access(
    user: User | None,
    root_node: FsNode,
    share: "SharedNode | None",
) -> User | None:
    """Validate access and return the user to record as ``requested_by``."""
    if share is not None:
        if share.root_fs_node_id != root_node.pk:
            raise exceptions.PermissionDenied(
                detail="The share does not point to the requested directory."
            )
        if not share.is_active:
            raise exceptions.PermissionDenied(detail="The share is not active anymore.")
        if user is not None and user.is_authenticated:
            return user
        return None

    if user is None or not has_download_access(user, root_node):
        raise exceptions.PermissionDenied(
            detail="You do not have access to this directory."
        )
    return user


def _find_active_job(root_node: FsNode) -> FsNodeArchiveJob | None:
    """Find an active job matching the current tree fingerprint."""
    root = FsNode.active.filter(pk=root_node.pk).first()
    if root is None:
        return None
    rows = _load_subtree(root)
    return FsNodeArchiveJob.objects.filter(
        root_node_uuid=root.pk,
        fingerprint=compute_fingerprint(rows),
        status__in=FsNodeArchiveJob.ACTIVE_STATUSES,
    ).first()


def _create_snapshot(
    root_node: FsNode,
    requested_by: User | None,
) -> FsNodeArchiveJob:
    with transaction.atomic():
        root = FsNode.active.filter(pk=root_node.pk).first()
        if root is None:
            raise exceptions.FsNodeNotFoundError(
                detail="The directory no longer exists."
            )
        if not root.is_directory:
            raise exceptions.FsNodeIsNotADirectoryError(
                detail="Only directories can be archived."
            )

        rows = _load_subtree(root)
        entries = build_manifest_entries(rows, root)
        file_entries = [
            entry
            for entry in entries
            if entry.entry_type == FsNodeArchiveItem.EntryType.FILE
        ]
        total_files = len(file_entries)
        total_bytes = sum(entry.size for entry in file_entries)
        _check_limits(total_files=total_files, total_bytes=total_bytes)

        fingerprint = compute_fingerprint(rows)
        existing = FsNodeArchiveJob.objects.filter(
            root_node_uuid=root.pk,
            fingerprint=fingerprint,
            status__in=FsNodeArchiveJob.ACTIVE_STATUSES,
        ).first()
        if existing is not None:
            return existing

        job = FsNodeArchiveJob.objects.create(
            requested_by=requested_by,
            root_node_uuid=root.pk,
            root_node_name=root.name,
            fingerprint=fingerprint,
            total_files=total_files,
            total_bytes=total_bytes,
        )
        items = []
        for position, entry in enumerate(entries):
            ref = entry.storage_object
            items.append(
                FsNodeArchiveItem(
                    job=job,
                    node_id=entry.node_id,
                    entry_type=entry.entry_type,
                    zip_path=entry.zip_path,
                    object_key=ref.key if ref else "",
                    storage_id=ref.storage_id if ref else None,
                    size=entry.size,
                    md5=entry.md5,
                    modified_at=entry.modified_at,
                    position=position,
                )
            )
        FsNodeArchiveItem.objects.bulk_create(items)
        return job


def create_archive_job(
    user: User | None,
    root_node: FsNode,
    *,
    share: "SharedNode | None" = None,
) -> FsNodeArchiveJob:
    """Create or reuse an archive job for a directory snapshot.

    The manifest is written in the same transaction as the job. If a concurrent
    deletion removes a node between the snapshot read and the manifest insert,
    the FK violation rolls the transaction back and the snapshot is retried
    once. If a concurrent request created the same job, the partial unique
    constraint fails and the existing job is returned.
    """
    requested_by = _check_access(user, root_node, share)

    for attempt in range(2):
        try:
            return _create_snapshot(root_node, requested_by)
        except IntegrityError:
            existing = _find_active_job(root_node)
            if existing is not None:
                return existing
            if attempt == 0:
                continue
            raise exceptions.ArchiveSnapshotConflict(
                detail=(
                    "The directory changed while its archive snapshot was being "
                    "created. Please retry the request."
                )
            )

    raise AssertionError("unreachable")


def cancel_archive_jobs_for_subtree(subtree_ids: list[uuid.UUID]) -> int:
    """Cancel active archive jobs whose root belongs to a deleted subtree.

    Deleting the manifest releases the ``PROTECT`` references so the deletion
    worker can remove the nodes. The archive file itself, if already built, is
    cleaned up later by the reaper.
    """
    subtree_ids = list(subtree_ids)
    if not subtree_ids:
        return 0

    with transaction.atomic():
        job_ids = list(
            FsNodeArchiveJob.objects.filter(
                root_node_uuid__in=subtree_ids,
                status__in=FsNodeArchiveJob.ACTIVE_STATUSES,
            ).values_list("pk", flat=True)
        )
        if not job_ids:
            return 0

        FsNodeArchiveItem.objects.filter(job_id__in=job_ids).delete()
        FsNodeArchiveJob.objects.filter(pk__in=job_ids).update(
            status=FsNodeArchiveJob.Status.CANCELLED,
            cancel_requested=True,
            finished_at=now(),
            locked_until=None,
            locked_by="",
            last_error="Archive root was deleted or its share was revoked.",
        )
        return len(job_ids)


def cancel_archive_jobs_for_root(root_node_uuid: uuid.UUID) -> int:
    """Cancel active archive jobs for a single root (for share revocation)."""
    return cancel_archive_jobs_for_subtree([root_node_uuid])
