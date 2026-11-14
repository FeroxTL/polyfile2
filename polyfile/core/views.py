import json
from dataclasses import asdict
from pathlib import PurePosixPath
from urllib.parse import urljoin

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.static import serve

from polyfile.apps.accounts.models import User
from polyfile.apps.accounts.utils import get_sidebar_urls
from polyfile.apps.storage.managers import get_fs_node_by_path_name
from polyfile.apps.storage.models import FsNode


def _resolve_initial_fs_node_id(user: User, path: str) -> str | None:
    """Resolve the UUID of the node the initial SPA route points to."""
    try:
        node = get_fs_node_by_path_name(user=user, path=PurePosixPath(path or "/"))
    except FsNode.DoesNotExist:
        return None
    return str(node.pk) if node is not None else None


@login_required
def fs_node_browse_view(request: HttpRequest, path: str = '') -> HttpResponse:
    """Static page for SPA."""
    dashboard_urls = json.dumps(list(map(asdict, get_sidebar_urls(request.user))))

    return render(request, "file_list.html", context={
        "dashboard_urls": dashboard_urls,
        # Lets the SPA load the initial directory by UUID instead of by path.
        "initial_fs_node": {
            "path": path or "/",
            "node_id": _resolve_initial_fs_node_id(request.user, path),
        },
    })


def serve_docs(request, path: str, document_root: str) -> HttpResponse | FileResponse:
    """Serves static page for documentation (only for development)."""
    try:
        return serve(request, path, document_root)
    except Http404:
        return serve(request, urljoin(path, 'index.html'), document_root)
