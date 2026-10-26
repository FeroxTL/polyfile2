import json
from dataclasses import asdict
from urllib.parse import urljoin

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.static import serve

from polyfile.apps.accounts.utils import get_sidebar_urls


@login_required
def fs_node_browse_view(request: HttpRequest, path: str = '') -> HttpResponse:
    """Static page for SPA."""
    dashboard_urls = json.dumps(list(map(asdict, get_sidebar_urls(request.user))))

    return render(request, "file_list.html", context={
        "dashboard_urls": dashboard_urls,
    })


def serve_docs(request, path: str, document_root: str) -> HttpResponse | FileResponse:
    """Serves static page for documentation (only for development)."""
    try:
        return serve(request, path, document_root)
    except Http404:
        return serve(request, urljoin(path, 'index.html'), document_root)
