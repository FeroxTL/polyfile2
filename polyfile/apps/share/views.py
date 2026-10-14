import json
import uuid
from pathlib import PurePosixPath

import marshmallow
from django import http
from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponseBase, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from polyfile.apps.share.models import SharedNode, ShareDownload
from polyfile.apps.share.schemas import (
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
from polyfile.apps.share.utils import validate_download_token
from polyfile.apps.storage.managers import get_user_fs_node_by_path
from polyfile.apps.storage.models import FsNode
from polyfile.apps.storage.schemas import ensure_absolute_path
from polyfile.apps.storage.services import serve_file
from polyfile.apps.storage.utils import get_fs_node_with_children
from polyfile.core import exceptions
from polyfile.core.rest.generics import AnonymousApiView, BaseApiView


def _parse_expires_at(request: HttpRequest):
    """Read and validate an optional ISO datetime from query or JSON body."""
    raw_expires_at = request.GET.get("expires_at")
    if raw_expires_at is None and request.body:
        try:
            body = json.loads(request.body)
        except json.JSONDecodeError:
            body = {}
        if isinstance(body, dict):
            raw_expires_at = body.get("expires_at")

    if raw_expires_at in (None, ""):
        return None

    expires_at = parse_datetime(str(raw_expires_at))
    if expires_at is None:
        raise marshmallow.ValidationError("Invalid datetime.", "expires_at")
    if timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at)
    return expires_at


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
            share = SharedNode.active.get(token=share_token)
            node_path: PurePosixPath = ensure_absolute_path(path)
            fs_node_with_children = get_fs_node_with_children(
                user=share.owner, 
                path=node_path,
                parent_fs_node=share.root_fs_node,
            )
            with SharedNodeTokenContext(share.token):
                return http.JsonResponse(data=self.response_serializer.dump(fs_node_with_children))
        except SharedNode.DoesNotExist:
            raise exceptions.NotFound(f"Share with token {share_token} does not exist.")


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
        node = FsNode.objects.get(id=fs_node_id)
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

    # TODO: We can not download directories now
    return render(request, "share/error.html", status=404, context={
        "error_message": "Can not download directory. Sorry for that",
    })


class CreateShareView(BaseApiView):
    """
    API view to create or update a public share.

    Allows a logged-in user to share a directory or file with others by 
    generating a public share entry in the system.
    """
    response_serializer = ShareListItemSchema()

    def post(self, request: http.HttpRequest, path: str = "") -> http.HttpResponse:
        """Create or update share."""
        node_path: PurePosixPath = ensure_absolute_path(path)
        try:
            fs_node = get_user_fs_node_by_path(user=request.user, path=node_path)
        except FsNode.DoesNotExist:
            fs_node = None

        if fs_node is None:
            raise marshmallow.ValidationError("FsNode not found.", "path")

        expires_at = _parse_expires_at(request)
        share = create_public_share(
            user=request.user,
            fs_node=fs_node,
            expires_at=expires_at,
        )

        with ShareListRequestContext(request):
            data = self.response_serializer.dump(share)

        #             "id": str(share.token),
        #             "url": get_public_share_url(request, share.token),
        #             "expires_at": share.expires_at,
        #             "revoked_at": share.revoked_at,

        return JsonResponse(data=data)


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
