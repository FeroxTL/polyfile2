import uuid

from django.contrib.auth.decorators import login_not_required, login_required
from django.http import (
    HttpRequest,
    response,
)
from django.views.decorators.csrf import csrf_exempt

from polyfile.apps.storage import schemas, services
from polyfile.apps.storage.decorators import catch_storage_exceptions
from polyfile.apps.storage.models import FsNode, TempUpload
from polyfile.contrib.backends.base import FsBackendBase
from polyfile.core.exceptions import NotFound


@login_required
@catch_storage_exceptions
def download_file_view(request: HttpRequest, pk: uuid.UUID):
    """Download file. Requires authentication and ownership."""
    try:
        fs_node: FsNode = FsNode.objects.get(type=FsNode.TypeChoices.FILE, id=pk)
    except FsNode.DoesNotExist:
        raise NotFound('File not found')

    # Use the new service to handle serving and permission checks
    return services.serve_file(
        request=request,
        fs_node=fs_node,
        skip_permission_check=False,
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
            fs_node__file='',
        )
    except TempUpload.DoesNotExist:
        raise NotFound('Upload not found')  # TODO: specify/translate error text

    storage: FsBackendBase = temp_upload.fs_node.file.storage
    storage.save_file(
        fs_node=temp_upload.fs_node,
        request=request,
    )

    # Mark TempUpload as complete
    temp_upload.mark_complete()

    return response.JsonResponse(schemas.FsNodeItemSchema().dump(temp_upload.fs_node))
