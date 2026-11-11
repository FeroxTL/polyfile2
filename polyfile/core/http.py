"""HTTP helpers shared by HTML pages and API endpoints."""

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

_JSON_FORMAT = "json"
_HTML_FORMAT = "html"

_ERROR_TITLES = {
    403: "Access denied",
    404: "Not found",
    410: "No longer available",
}


def wants_html(request: HttpRequest) -> bool:
    """Return whether the client explicitly prefers an HTML document.

    Browsers send ``Accept: text/html`` when the user navigates to a URL, while
    API clients and the archive polling script send ``Accept: application/json``.
    Unknown clients (``*/*``) keep receiving JSON so existing API behavior is
    unchanged.
    """
    if (fmt := request.GET.get("format", "").lower()) in (_JSON_FORMAT, _HTML_FORMAT):
        return fmt == _HTML_FORMAT

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return False

    accept = request.headers.get("Accept", "")
    return "text/html" in accept and "application/json" not in accept


def vary_on_accept(response: HttpResponse) -> HttpResponse:
    """Mark a response as content-negotiated on the ``Accept`` header.

    Uses ``patch_vary_headers`` so headers added by middleware or decorators
    (for example ``Vary: Cookie`` from ``login_required``) are preserved.
    """
    patch_vary_headers(response, ("Accept",))
    return response


def render_error_page(
    request: HttpRequest,
    *,
    status: int,
    message: str,
    title: str | None = None,
) -> HttpResponse:
    """Render a standalone HTML error page for browser navigation."""
    return vary_on_accept(render(
        request,
        "error.html",
        status=status,
        context={
            "title": title or _ERROR_TITLES.get(status, "Request failed"),
            "message": message,
        },
    ))
