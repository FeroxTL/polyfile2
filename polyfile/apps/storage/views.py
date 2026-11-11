import uuid

from django.contrib.auth.decorators import login_not_required, login_required
from django.http import (
    HttpRequest,
    HttpResponseRedirect,
    response,
)
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from polyfile.apps.storage import (
    archive,
    archive_delivery,
    schemas,
    services,
    upload_service,
)
from polyfile.apps.storage.decorators import catch_storage_exceptions
from polyfile.apps.storage.models import FsNode, FsNodeArchiveJob, TempUpload
from polyfile.core import exceptions
from polyfile.core.exceptions import NotFound


def _archive_error_response(request: HttpRequest, exc: exceptions.HttpException):
    return render(
        request,
        "storage/archive_error.html",
        status=exc.status_code,
        context={"message": exc.detail},
    )


@login_required
@catch_storage_exceptions
def download_file_view(request: HttpRequest, pk: uuid.UUID):
    """Download a file synchronously or start a directory archive job."""
    try:
        fs_node: FsNode = FsNode.active.get(id=pk)
    except FsNode.DoesNotExist:
        raise NotFound('File not found')

    if fs_node.is_directory:
        job = archive.create_archive_job(request.user, fs_node)
        status_url = request.build_absolute_uri(
            reverse("archive_job_status", kwargs={"job_id": job.pk})
        )
        file_url = request.build_absolute_uri(
            reverse("archive_job_file", kwargs={"job_id": job.pk})
        )

        if request.GET.get("format", "").lower() == "json":
            return archive_delivery.accepted_response(
                job,
                status_url=status_url,
                file_url=file_url,
            )

        redirect_response = HttpResponseRedirect(
            reverse("archive_job_wait", kwargs={"job_id": job.pk})
        )
        redirect_response.status_code = 303
        return redirect_response

    # Use the new service to handle serving and permission checks
    return services.serve_file(
        request=request,
        fs_node=fs_node,
        skip_permission_check=False,
    )


@login_required
def archive_job_wait_view(request: HttpRequest, job_id: uuid.UUID):
    """HTML page that waits for an archive and redirects to the ZIP."""
    try:
        job, _root = archive_delivery.get_archive_job_for_owner(
            request.user,
            job_id,
        )
        archive_delivery.expire_if_needed(job)
    except exceptions.HttpException as exc:
        return _archive_error_response(request, exc)

    status_url = reverse("archive_job_status", kwargs={"job_id": job.pk})
    file_url = reverse("archive_job_file", kwargs={"job_id": job.pk})

    if job.status == FsNodeArchiveJob.Status.READY:
        redirect_response = HttpResponseRedirect(file_url)
        redirect_response.status_code = 303
        return redirect_response

    if job.status in (
        FsNodeArchiveJob.Status.FAILED,
        FsNodeArchiveJob.Status.CANCELLED,
        FsNodeArchiveJob.Status.EXPIRED,
    ):
        return render(
            request,
            "storage/archive_error.html",
            status=exceptions.ArchiveUnavailable.status_code,
            context={
                "message": job.last_error or "The archive is no longer available.",
            },
        )

    return render(
        request,
        "storage/archive_wait.html",
        context={
            "job": job,
            "status_url": status_url,
            "file_url": file_url,
            "retry_after": archive_delivery.get_retry_after(),
        },
    )


@login_required
@catch_storage_exceptions
def archive_job_status_view(request: HttpRequest, job_id: uuid.UUID):
    """JSON status endpoint used by the waiting page and API clients."""
    job, _root = archive_delivery.get_archive_job_for_owner(
        request.user,
        job_id,
    )
    archive_delivery.expire_if_needed(job)

    return archive_delivery.status_response(
        job,
        status_url=request.build_absolute_uri(
            reverse("archive_job_status", kwargs={"job_id": job.pk})
        ),
        file_url=request.build_absolute_uri(
            reverse("archive_job_file", kwargs={"job_id": job.pk})
        ),
    )


@login_required
@catch_storage_exceptions
def archive_job_file_view(request: HttpRequest, job_id: uuid.UUID):
    """Serve a ready archive, or ask the client to retry while it is built."""
    job, _root = archive_delivery.get_archive_job_for_owner(
        request.user,
        job_id,
    )
    archive_delivery.expire_if_needed(job)

    status_url = request.build_absolute_uri(
        reverse("archive_job_status", kwargs={"job_id": job.pk})
    )
    file_url = request.build_absolute_uri(
        reverse("archive_job_file", kwargs={"job_id": job.pk})
    )

    if job.status in (
        FsNodeArchiveJob.Status.PENDING,
        FsNodeArchiveJob.Status.RUNNING,
    ):
        return archive_delivery.accepted_response(
            job,
            status_url=status_url,
            file_url=file_url,
        )

    if job.status != FsNodeArchiveJob.Status.READY:
        raise exceptions.ArchiveUnavailable(
            detail=job.last_error or "The archive is no longer available.",
        )

    return archive_delivery.serve_archive(
        job,
        head=request.method == "HEAD",
    )


@login_not_required
@csrf_exempt
@catch_storage_exceptions
def upload_file_view(request: HttpRequest, token: str):
    """
    Upload file.

    User is authenticated with `token`, login not required.
    """
    try:
        temp_upload: TempUpload = TempUpload.objects.select_related('fs_node').get(
            token=token,
            status=TempUpload.Status.UPLOADING,
            fs_node__object_key='',
            fs_node__deleted_at__isnull=True,
        )
    except TempUpload.DoesNotExist:
        raise NotFound('Upload not found')  # TODO: specify/translate error text

    upload_service.save_upload(
        fs_node=temp_upload.fs_node,
        request=request,
    )

    # Mark TempUpload as complete
    temp_upload.mark_complete()

    return response.JsonResponse(schemas.FsNodeItemSchema().dump(temp_upload.fs_node))
