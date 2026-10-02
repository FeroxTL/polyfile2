from pathlib import PurePosixPath

from django.contrib.auth.decorators import login_not_required
from django.http import HttpRequest, HttpResponse, HttpResponseBase
from django.shortcuts import render

from polyfile.apps.share.models import SharedNode, ShareDownload
from polyfile.apps.share.utils import validate_download_token
from polyfile.apps.storage.models import FsNode
from polyfile.apps.storage.schemas import ensure_absolute_path
from polyfile.apps.storage.services import serve_file
from polyfile.apps.storage.utils import get_fs_node_with_children
from polyfile.core import exceptions


@login_not_required
def browse_share(request: HttpRequest, share_token: str, path: str = "") -> HttpResponse:
    """
    Renders an HTML page showing the shared content.
    """
    try:
        share = SharedNode.active.get(token=share_token)
        node_path: PurePosixPath = ensure_absolute_path(path)
        node_info = get_fs_node_with_children(user=share.owner, path=node_path, parent_fs_node=share.root_fs_node)
    except (SharedNode.DoesNotExist, exceptions.HttpException) as e:
        return render(request, "share/error.html", context={
            "error_message": str(e),
        })

    return render(request, "share/public_share.html", context={
        "share" : share,
        "node_info": node_info,
    })


@login_not_required
def public_share_download(
        request: HttpRequest,
        share_token: str,
        fs_node_pk: str,
        time_offset: str,
        signature: str,
) -> HttpResponseBase:
    """
    Handles public file downloads using a signed token.

    The view validates the signed token to retrieve the share and the specific FsNode,
    checks if the share is active, logs the download, and serves the file using the storage service.
    """
    if not validate_download_token(share_token, fs_node_pk, time_offset, signature):
        return render(request, "share/error.html", status=404, context={
            "error_message": "This share does not exist.",
        })

    try:
        # Find an active ShareNode
        share = SharedNode.active.get(token=share_token)
        node = FsNode.objects.get(id=fs_node_pk)
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
