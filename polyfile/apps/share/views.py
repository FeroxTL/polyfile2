import json
import uuid
from pathlib import PurePosixPath

import marshmallow
from django import http
from django.contrib.auth.decorators import login_not_required
from django.http import (
    HttpRequest,
    HttpResponseBase,
    HttpResponseRedirect,
    JsonResponse,
)
from django.shortcuts import render
from django.utils import timezone

from polyfile.apps.share.models import SharedNode, ShareDownload
from polyfile.apps.share.schemas import (
    CreateShareRequestSchema,
    SharedNodeTokenContext,
    ShareFsNodeListResponseSchema,
    ShareListItemSchema,
    ShareListRequestContext,
    ShareListResponseSchema,
)
from polyfile.apps.share.services import (
    SHARE_LIST_PAGE_SIZE,
    create_public_share,
    hard_delete_public_share,
    list_user_shares,
    revoke_public_share,
)
from polyfile.apps.share.utils import (
    share_archive_url,
    validate_download_token,
)
from polyfile.apps.storage import archive_delivery
from polyfile.apps.storage.archive import create_archive_job
from polyfile.apps.storage.models import FsNode, FsNodeArchiveJob
from polyfile.apps.storage.schemas import ensure_absolute_path
from polyfile.apps.storage.services import serve_file
from polyfile.apps.storage.utils import get_fs_node_with_children
from polyfile.core import exceptions
from polyfile.core.http import vary_on_accept, wants_html
from polyfile.core.rest.generics import AnonymousApiView, BaseApiView


def _positive_int_param(request: HttpRequest, name: str, default: int) -> int:
    """Parse a positive integer query parameter."""
    raw_value = request.GET.get(name)
    if raw_value in (None, ""):
        return default

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        raise marshmallow.ValidationError("Must be an integer.", name)

    if value < 1:
        raise marshmallow.ValidationError("Must be greater than 0.", name)
    return value


class GetShareDetailApiView(AnonymousApiView):
    """
    API view to retrieve the details of a public share.

    This view allows anyone with a valid share token to see the structure 
    of the files and folders included in that share.
    """
    response_serializer = ShareFsNodeListResponseSchema()

    def get(self, request: http.HttpRequest, share_token: str, path: str = "") -> http.HttpResponse:
        """Retrieve the details of a public share."""
        try:
            share = SharedNode.active.get(token=share_token, root_fs_node__deleted_at__isnull=True)
            node_path: PurePosixPath = ensure_absolute_path(path)
            fs_node_with_children = get_fs_node_with_children(
                user=share.owner, 
                path=node_path,
                parent_fs_node=share.root_fs_node,
            )
            # TODO: we already checked parent, can skip checking child
            if fs_node_with_children.current and getattr(fs_node_with_children.current, 'deleted_at', None) is not None:
                raise exceptions.NotFound(f"Share with token {share_token} does not exist.")
            with SharedNodeTokenContext(share):
                return http.JsonResponse(data=self.response_serializer.dump(fs_node_with_children))
        except SharedNode.DoesNotExist:
            raise exceptions.NotFound(f"Share with token {share_token} does not exist.")


def _share_archive_urls(
    request: HttpRequest,
    share: SharedNode,
    job: FsNodeArchiveJob,
) -> tuple[str, str]:
    """Build absolute signed status and file URLs for a share archive."""
    status_url = request.build_absolute_uri(share_archive_url(
        "share-archive-status",
        share.token,
        share.root_fs_node_id,
        job.pk,
    ))
    file_url = request.build_absolute_uri(share_archive_url(
        "share-archive-file",
        share.token,
        share.root_fs_node_id,
        job.pk,
    ))
    return status_url, file_url


@login_not_required
def public_share_download(
        request: HttpRequest,
        share_token: str,
        fs_node_id: str,
        time_offset: str,
        signature: str,
) -> HttpResponseBase:
    """
    Handles public file downloads using a signed token.

    The view validates the signed token to retrieve the share and the specific FsNode,
    checks if the share is active, logs the download, and serves the file using the storage service.
    """
    if not validate_download_token(share_token, fs_node_id, time_offset, signature):
        return render(request, "share/error.html", status=404, context={
            "error_message": "This share does not exist.",
        })

    try:
        # Find an active ShareNode
        share = SharedNode.active.get(token=share_token)
        node = FsNode.active.get(id=fs_node_id)
        if node.deleted_at is not None or share.root_fs_node.deleted_at is not None:
            raise FsNode.DoesNotExist
    except (FsNode.DoesNotExist, SharedNode.DoesNotExist):
        return render(request, "share/error.html", status=404, context={
            "error_message": "This share is not active anymore.",
        })

    if node.is_file:
        # Log the download
        ShareDownload.objects.create(
            share=share,
            ip=request.META.get("REMOTE_ADDR"),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        return serve_file(
            request=request,
            fs_node=node,
            skip_permission_check=True,
        )

    if node.pk != share.root_fs_node_id:
        return render(request, "share/error.html", status=404, context={
            "error_message": "Only the shared directory itself can be archived.",
        })

    try:
        job = create_archive_job(None, node, share=share)
    except exceptions.HttpException as exc:
        return render(request, "share/error.html", status=exc.status_code, context={
            "error_message": exc.detail,
        })

    status_url, file_url = _share_archive_urls(request, share, job)

    if request.GET.get("format", "").lower() == "json":
        return archive_delivery.accepted_response(
            job,
            status_url=status_url,
            file_url=file_url,
        )

    redirect_response = HttpResponseRedirect(share_archive_url(
        "share-archive-wait",
        share.token,
        node.pk,
        job.pk,
    ))
    redirect_response.status_code = 303
    return redirect_response


def _get_share_for_archive(
    share_token: uuid.UUID,
    time_offset: str,
    signature: str,
):
    """Load and validate a share for one of its archive job URLs."""
    try:
        share = SharedNode.objects.get(token=share_token)
    except SharedNode.DoesNotExist:
        raise exceptions.NotFound(f"Share with token {share_token} does not exist.")

    if not validate_download_token(
        str(share.token),
        str(share.root_fs_node_id),
        time_offset,
        signature,
    ):
        raise exceptions.NotFound("Invalid or expired archive link.")

    return share


@login_not_required
def share_archive_wait_view(
    request: HttpRequest,
    share_token: uuid.UUID,
    job_id: uuid.UUID,
    time_offset: str,
    signature: str,
):
    """HTML waiting page for a public directory archive."""
    try:
        share = _get_share_for_archive(share_token, time_offset, signature)
        job, _root = archive_delivery.get_archive_job_for_share(share, job_id)
        archive_delivery.expire_if_needed(job)
    except exceptions.HttpException as exc:
        return render(request, "share/error.html", status=exc.status_code, context={
            "error_message": exc.detail,
        })

    status_url, file_url = _share_archive_urls(request, share, job)

    if job.status == FsNodeArchiveJob.Status.READY:
        redirect_response = HttpResponseRedirect(file_url)
        redirect_response.status_code = 303
        return redirect_response

    if job.status in (
        FsNodeArchiveJob.Status.FAILED,
        FsNodeArchiveJob.Status.CANCELLED,
        FsNodeArchiveJob.Status.EXPIRED,
    ):
        return render(request, "share/error.html", status=410, context={
            "error_message": job.last_error or "The archive is no longer available.",
        })

    return render(request, "storage/archive_wait.html", context={
        "job": job,
        "status_url": status_url,
        "file_url": file_url,
        "retry_after": archive_delivery.get_retry_after(),
    })


@login_not_required
def share_archive_status_view(
    request: HttpRequest,
    share_token: uuid.UUID,
    job_id: uuid.UUID,
    time_offset: str,
    signature: str,
):
    """JSON status endpoint for a public directory archive."""
    try:
        share = _get_share_for_archive(share_token, time_offset, signature)
        job, _root = archive_delivery.get_archive_job_for_share(share, job_id)
        archive_delivery.expire_if_needed(job)
    except exceptions.HttpException as exc:
        return JsonResponse(
            {
                "error_id": exc.error_code,
                "description": exc.description,
                "detail": exc.detail,
            },
            status=exc.status_code,
        )

    status_url, file_url = _share_archive_urls(request, share, job)
    return archive_delivery.status_response(
        job,
        status_url=status_url,
        file_url=file_url,
    )


@login_not_required
def share_archive_file_view(
    request: HttpRequest,
    share_token: uuid.UUID,
    job_id: uuid.UUID,
    time_offset: str,
    signature: str,
):
    """Serve a public directory archive."""
    try:
        share = _get_share_for_archive(share_token, time_offset, signature)
        job, _root = archive_delivery.get_archive_job_for_share(share, job_id)
        archive_delivery.expire_if_needed(job)
        status_url, file_url = _share_archive_urls(request, share, job)

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

        if request.method != "HEAD":
            ShareDownload.objects.create(
                share=share,
                ip=request.META.get("REMOTE_ADDR"),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
            )
        return archive_delivery.serve_archive(
            job,
            head=request.method == "HEAD",
        )
    except exceptions.HttpException as exc:
        if wants_html(request):
            return vary_on_accept(
                render(request, "share/error.html", status=exc.status_code, context={
                    "error_message": exc.detail,
                }),
            )
        return vary_on_accept(JsonResponse(
            {
                "error_id": exc.error_code,
                "description": exc.description,
                "detail": exc.detail,
            },
            status=exc.status_code,
        ))


class RevokeShareView(BaseApiView):
    """
    API view to revoke a public share.

    Allows a logged-in user to invalidate a specific share, making it 
    no longer accessible via its public token.
    """
    @staticmethod
    def post(request: http.HttpRequest, share_token: uuid.UUID) -> http.HttpResponse:
        """Revoke a share owned by the current user."""
        try:
            revoke_public_share(user=request.user, share_token=share_token)
        except SharedNode.DoesNotExist:
            raise exceptions.NotFound(f"Share with token {share_token} does not exist.")

        return http.HttpResponse(status=204)


class PermanentDeleteShareView(BaseApiView):
    """
    API view to permanently delete a public share.

    Allows a logged-in user to remove a share entry and its metadata 
    from the system entirely.
    """
    @staticmethod
    def delete(request: http.HttpRequest, share_token: uuid.UUID) -> http.HttpResponse:
        """Permanently delete a share owned by the current user."""
        try:
            hard_delete_public_share(user=request.user, share_token=share_token)
        except SharedNode.DoesNotExist:
            raise exceptions.NotFound(f"Share with token {share_token} does not exist.")

        return http.HttpResponse(status=204)


class ListSharesApiView(BaseApiView):
    """
    API view to list all shares owned by the current user.

    Supports filtering by status (e.g., 'active', 'revoked') and 
    pagination via query parameters.
    """
    response_serializer = ShareListResponseSchema()

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        """List the current user's shares."""
        status = request.GET.get("status", "all")
        page = _positive_int_param(request, "page", 1)

        try:
            shares, total = list_user_shares(
                user=request.user,
                status=status,
                page=page,
            )
        except ValueError as exc:
            raise marshmallow.ValidationError(str(exc), "status")

        with ShareListRequestContext(request):
            data = self.response_serializer.dump({
                "items": shares,
                "page": page,
                "page_size": SHARE_LIST_PAGE_SIZE,
                "total": total,
                "has_next": page * SHARE_LIST_PAGE_SIZE < total,
            })

        return http.JsonResponse(data=data)

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        """Create or update a share by node UUID."""
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            raise exceptions.BadRequest("Invalid JSON body")

        try:
            params = CreateShareRequestSchema().load(body)
        except marshmallow.ValidationError as e:
            raise exceptions.FieldValidationError(detail=e.messages)

        try:
            fs_node = FsNode.active.get(id=params["node_id"], owner=request.user)
        except FsNode.DoesNotExist:
            raise exceptions.NotFound(f'FsNode "{params["node_id"]}" not found.')

        expires_at = params.get("expires_at")
        if expires_at is not None and timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)

        share = create_public_share(
            user=request.user,
            fs_node=fs_node,
            expires_at=expires_at,
        )

        with ShareListRequestContext(request):
            data = ShareListItemSchema().dump(share)

        return http.JsonResponse(data=data)
