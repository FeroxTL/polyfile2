from django.http import (
    FileResponse,
    Http404,
    HttpRequest,
    HttpResponseNotModified,
)
from django.http.response import HttpResponseBase
from django.utils.http import http_date
from django.utils.translation import gettext as _
from django.views.static import was_modified_since

from polyfile.apps.accounts.models import User
from polyfile.apps.storage.models import FsNode
from polyfile.core.exceptions import PermissionDenied


def has_download_access(user, fs_node: FsNode) -> bool:
    """
    Check if user has access to download the file.

    Currently only owner can download. In the future, this can be extended
    to support shared access, group permissions, etc.
    """
    return isinstance(user, User) and fs_node.owner_id == user.id

def serve_file(request: HttpRequest, fs_node: FsNode, skip_permission_check: bool = False) -> HttpResponseBase:
    """Serve static files below a given point in the directory structure."""
    # TODO: this only handles FileStorageBackend

    if fs_node.is_directory:
        raise Http404(_('Directory indexes are not allowed here.'))

    if not skip_permission_check and not has_download_access(request.user, fs_node):
        # We assume the user is provided in the request (e.g. via auth)
        # If it's a public share, we handle the user context in the view
        raise PermissionDenied(_('You do not have access to this file'))

    # Respect the If-Modified-Since header.
    fs_node_timestamp = fs_node.modified_at.timestamp()
    if not was_modified_since(request.META.get('HTTP_IF_MODIFIED_SINCE'), fs_node_timestamp):
        return HttpResponseNotModified()

    return FileResponse(
        fs_node.file.open('rb'),
        filename=fs_node.name,
        content_type=fs_node.mime_type or 'core/octet-stream',
        as_attachment=request.GET.get('disposition') == 'attachment',
        headers={'Last-Modified': http_date(fs_node_timestamp)},
    )
