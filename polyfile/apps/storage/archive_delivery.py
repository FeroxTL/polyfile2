"""Delivery helpers for built directory archives.

The archive job is always checked against the *current* root node: the job only
stores ``root_node_uuid`` and ``requested_by`` is not an access-control field.
Every request therefore re-checks that the root is still active and that the
caller owns it (or that a public share is still valid).
"""

import uuid
from urllib.parse import quote

from django.conf import settings
from django.http import FileResponse, HttpResponse, JsonResponse
from django.http.response import HttpResponseBase
from django.utils.http import content_disposition_header
from django.utils.timezone import now

from polyfile.apps.accounts.models import User
from polyfile.apps.storage.archive_backend import get_archive_backend
from polyfile.apps.storage.models import FsNode, FsNodeArchiveJob
from polyfile.apps.storage.services import has_download_access
from polyfile.core import exceptions

DEFAULT_RETRY_AFTER = 2


def get_retry_after() -> int:
    """Return the polling interval advertised to clients, in seconds."""
    value = getattr(
        settings,
        "DIRECTORY_ARCHIVE_RETRY_AFTER",
        DEFAULT_RETRY_AFTER,
    )
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER


def get_active_archive_root(job: FsNodeArchiveJob) -> FsNode:
    """Return the still-active directory a job was built for."""
    root = FsNode.active.filter(pk=job.root_node_uuid).first()
    if root is None or not root.is_directory:
        raise exceptions.ArchiveUnavailable(
            detail="The directory for this archive was deleted.",
        )
    return root


def get_archive_job_for_owner(
    user: User,
    job_id: uuid.UUID,
) -> tuple[FsNodeArchiveJob, FsNode]:
    """Load a job for its owner.

    A job belonging to somebody else is reported as ``404`` instead of ``403``
    so the endpoint cannot be used to enumerate other users' archive jobs.
    """
    try:
        job = FsNodeArchiveJob.objects.get(pk=job_id)
    except FsNodeArchiveJob.DoesNotExist:
        raise exceptions.NotFound("Archive job not found")

    root = FsNode.active.filter(pk=job.root_node_uuid).first()
    if root is None:
        # There is no current owner to check once the root is gone. Only the
        # original requester learns that the job existed; everyone else gets a
        # 404 and cannot probe for deleted jobs.
        if job.requested_by_id == user.id:
            raise exceptions.ArchiveUnavailable(
                detail="The directory for this archive was deleted.",
            )
        raise exceptions.NotFound("Archive job not found")

    if not root.is_directory:
        raise exceptions.ArchiveUnavailable(
            detail="The directory for this archive was deleted.",
        )
    if not has_download_access(user, root):
        raise exceptions.NotFound("Archive job not found")
    return job, root


def get_archive_job_for_share(
    share,
    job_id: uuid.UUID,
) -> tuple[FsNodeArchiveJob, FsNode]:
    """Load a job through an active public share of its root."""
    try:
        job = FsNodeArchiveJob.objects.get(pk=job_id)
    except FsNodeArchiveJob.DoesNotExist:
        raise exceptions.NotFound("Archive job not found")

    if job.root_node_uuid != share.root_fs_node_id:
        raise exceptions.NotFound("Archive job not found")

    root = get_active_archive_root(job)
    if not share.is_active:
        raise exceptions.ArchiveUnavailable(
            detail="The share is not active anymore.",
        )
    return job, root


def is_archive_expired(job: FsNodeArchiveJob) -> bool:
    """Return whether a ready archive has outlived its hard TTL."""
    return (
        job.status == FsNodeArchiveJob.Status.READY
        and job.expires_at is not None
        and job.expires_at <= now()
    )


def expire_if_needed(job: FsNodeArchiveJob) -> FsNodeArchiveJob:
    """Move a TTL-expired job to ``expired``.

    The archive file is intentionally left for the reaper: deleting it here
    could race with an in-flight download. The file is no longer reachable
    because every delivery path checks the status first.
    """
    if not is_archive_expired(job):
        return job

    updated = FsNodeArchiveJob.objects.filter(
        pk=job.pk,
        status=FsNodeArchiveJob.Status.READY,
    ).update(
        status=FsNodeArchiveJob.Status.EXPIRED,
        last_error="Archive expired.",
    )
    if updated:
        job.status = FsNodeArchiveJob.Status.EXPIRED
        job.last_error = "Archive expired."
    else:
        # Another worker or request may have changed the state concurrently.
        try:
            job.refresh_from_db(fields=("status", "last_error"))
        except FsNodeArchiveJob.DoesNotExist as exc:
            raise exceptions.ArchiveUnavailable(
                detail="The archive is no longer available.",
            ) from exc
    return job


def archive_download_filename(job: FsNodeArchiveJob) -> str:
    """Build a safe ``<root_name>.zip`` download filename."""
    name = (job.root_node_name or "archive").replace("\\", "_")
    name = name.replace("/", "_").replace("\x00", "").strip()
    if not name or name in (".", ".."):
        name = "archive"
    return f"{name[:250]}.zip"


def _isoformat(value) -> str | None:
    return value.isoformat() if value is not None else None


def build_status_payload(
    job: FsNodeArchiveJob,
    *,
    status_url: str,
    file_url: str | None = None,
) -> dict:
    """Serialize job state for both the API and the polling page."""
    ready = job.status == FsNodeArchiveJob.Status.READY
    retry_after = (
        get_retry_after()
        if job.status in (
            FsNodeArchiveJob.Status.PENDING,
            FsNodeArchiveJob.Status.RUNNING,
        )
        else None
    )
    available_file_url = file_url if ready and file_url else None

    return {
        "job_id": str(job.pk),
        "status": job.status,
        "state": job.status,
        "root_node_uuid": str(job.root_node_uuid),
        "root_node_name": job.root_node_name,
        "total_files": job.total_files,
        "processed_files": job.processed_files,
        "total_bytes": job.total_bytes,
        "processed_bytes": job.processed_bytes,
        "last_error": job.last_error,
        "created_at": _isoformat(job.created_at),
        "started_at": _isoformat(job.started_at),
        "finished_at": _isoformat(job.finished_at),
        "expires_at": _isoformat(job.expires_at),
        "retry_after": retry_after,
        "status_url": status_url,
        "file_url": available_file_url,
        "download_url": available_file_url,
    }


def _with_polling_headers(
    response: HttpResponseBase,
    payload: dict,
) -> HttpResponseBase:
    if payload["retry_after"] is not None:
        response["Retry-After"] = str(payload["retry_after"])
    response["Cache-Control"] = "no-store"
    return response


def accepted_response(
    job: FsNodeArchiveJob,
    *,
    status_url: str,
    file_url: str | None = None,
) -> HttpResponse:
    """Return ``202 Accepted`` with job metadata and polling hints."""
    payload = build_status_payload(job, status_url=status_url, file_url=file_url)
    response = JsonResponse(payload, status=202)
    response["Location"] = status_url
    return _with_polling_headers(response, payload)


def status_response(
    job: FsNodeArchiveJob,
    *,
    status_url: str,
    file_url: str | None = None,
) -> HttpResponse:
    """Return ``200 OK`` with the current job state."""
    payload = build_status_payload(job, status_url=status_url, file_url=file_url)
    response = JsonResponse(payload, status=200)
    return _with_polling_headers(response, payload)


def serve_archive(
    job: FsNodeArchiveJob,
    *,
    head: bool = False,
) -> HttpResponseBase:
    """Serve a ready archive through nginx or a Django ``FileResponse``.

    ``HEAD`` requests are answered without opening or streaming the file: they
    are used by the SPA as a cheap preflight before navigating to the download
    URL, so a missing archive is reported while the modal is still visible.
    """
    backend = get_archive_backend()
    if not job.archive_key or not backend.exists(job.archive_key):
        raise exceptions.ArchiveUnavailable(
            detail="The archive file is no longer available.",
        )

    filename = archive_download_filename(job)

    if head:
        response = HttpResponse(status=200, content_type="application/zip")
        response["Content-Disposition"] = content_disposition_header(
            True,
            filename,
        )
        return response

    FsNodeArchiveJob.objects.filter(pk=job.pk).update(last_accessed_at=now())

    accel_prefix = getattr(settings, "ARCHIVE_ACCEL_PREFIX", "") or ""

    if accel_prefix:
        response = HttpResponse(status=200, content_type="application/zip")
        response["X-Accel-Redirect"] = (
            f"{accel_prefix.rstrip('/')}/{quote(job.archive_key, safe='/')}"
        )
        response["Content-Disposition"] = content_disposition_header(
            True,
            filename,
        )
        return response

    try:
        fileobj = backend.open(job.archive_key)
    except FileNotFoundError as exc:
        raise exceptions.ArchiveUnavailable(
            detail="The archive file is no longer available.",
        ) from exc

    return FileResponse(
        fileobj,
        content_type="application/zip",
        as_attachment=True,
        filename=filename,
    )
