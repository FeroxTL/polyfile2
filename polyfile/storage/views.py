import uuid
from pathlib import Path

from django.contrib.auth.decorators import login_not_required, login_required
from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponseNotModified,
    response,
)
from django.utils.http import http_date
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.static import was_modified_since

from polyfile.accounts.models import User
from polyfile.application.api_v1 import api_v1_schemas
from polyfile.application.exceptions import NotFound, PermissionDenied
from polyfile.backends.base import BaseStorageBackend
from polyfile.storage.decorators import catch_storage_exceptions
from polyfile.storage.models import ChunkedStatus, FsNode, FsNodeTypeChoices, TempUpload


def serve(request: HttpRequest, fs_node: FsNode, as_attachment: bool = False):
    """Serve static files below a given point in the directory structure."""
    # TODO: this is only for files on local disk
    fullpath = Path(fs_node.file.path)

    if fs_node.is_directory or fullpath.is_dir():
        raise Http404(_('Directory indexes are not allowed here.'))

    if not fullpath.exists():
        raise Http404(_('“%(path)s” does not exist') % {"path": fullpath})

    # Respect the If-Modified-Since header.
    fs_node_timestamp = fs_node.modified_at.timestamp()
    if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'), fs_node_timestamp):
        return HttpResponseNotModified()

    resp = FileResponse(
        fullpath.open('rb'),
        filename=fs_node.name,
        content_type=fs_node.mime_type or 'application/octet-stream',
        as_attachment=as_attachment,
    )
    resp.headers['Last-Modified'] = http_date(fs_node_timestamp)
    return resp


def has_download_access(user: User, fs_node: FsNode) -> bool:
    """
    Check if user has access to download the file.

    Currently only owner can download. In the future, this can be extended
    to support shared access, group permissions, etc.
    """
    return fs_node.owner_id == user.id


@login_required
@catch_storage_exceptions
def download_file_view(request: HttpRequest, pk: uuid.UUID):
    """Download file. Requires authentication and ownership."""
    try:
        fs_node: FsNode = FsNode.objects.get(type=FsNodeTypeChoices.FILE, id=pk)
    except FsNode.DoesNotExist:
        raise NotFound('File not found')

    if not has_download_access(request.user, fs_node):
        raise PermissionDenied('You do not have access to this file')

    return serve(
        request=request,
        fs_node=fs_node,
        as_attachment=request.GET.get('disposition') == 'attachment',
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
            status=ChunkedStatus.UPLOADING,
            fs_node__file='',
        )
    except TempUpload.DoesNotExist:
        raise NotFound('Upload not found')  # TODO: specify/translate error text

    storage: BaseStorageBackend = temp_upload.fs_node.file.storage
    storage.save_file(
        fs_node=temp_upload.fs_node,
        request=request,
    )

    # Mark TempUpload as complete
    temp_upload.mark_complete()

    return response.JsonResponse(api_v1_schemas.FsNodeItemSchema().dump(temp_upload.fs_node))
