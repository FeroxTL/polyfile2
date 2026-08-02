import uuid
from pathlib import Path

from django.contrib.auth.decorators import login_not_required
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

from polyfile.application.api_v1 import api_v1_schemas
from polyfile.application.exceptions import NotFound, PermissionDenied
from polyfile.storage.backends import BaseStorageBackend
from polyfile.storage.decorators import catch_storage_exceptions
from polyfile.storage.models import ChunkedStatus, FsNode, FsNodeTypeChoices, TempUpload
from polyfile.storage.tokens import default_token_generator


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


@catch_storage_exceptions
def download_file_view(request: HttpRequest, pk: uuid.UUID, token: str):
    """Download file."""
    try:
        fs_node: FsNode = FsNode.objects.get(type=FsNodeTypeChoices.FILE, id=pk)
    except FsNode.DoesNotExist:
        raise NotFound('File not found')  # TODO: specify/translate error text

    if not default_token_generator.check_token(fs_node=fs_node, token=token):
        raise PermissionDenied('Invalid token')  # TODO: specify/translate error text

    return serve(
        request=request,
        fs_node=fs_node,
        as_attachment=request.GET.get('disposition') == 'attachment',
    )


@login_not_required
@csrf_exempt
@catch_storage_exceptions
def upload_file_view(request: HttpRequest, token: str):
    """Upload file."""
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
