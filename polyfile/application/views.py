import json
from dataclasses import asdict

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from polyfile.accounts.utils import get_sidebar_urls


@login_required
def files_dashboard_view(request: HttpRequest, path: str = '') -> HttpResponse:
    """Static page for SPA."""
    dashboard_urls = json.dumps(list(map(asdict, get_sidebar_urls(request.user))))

    return render(request, "file_list.html", context={
        'dashboard_urls': dashboard_urls,
    })
