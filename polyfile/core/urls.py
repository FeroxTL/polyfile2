from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import URLPattern, URLResolver, include, path, reverse_lazy
from django.views.generic import RedirectView

from polyfile.apps.storage.views import download_file_view, upload_file_view
from polyfile.core import api
from polyfile.core.views import fs_node_browse_view, serve_docs

# APIs
api_patterns = [
    path("dashboard-context/", api.DashboardContextView.as_view()),
    path("api/v1/user/logout/", api.LogoutView.as_view()),
    path("api/", include("polyfile.apps.storage.urls")),
    # LocalDiskBackend urls todo: move to storage app? make dynamic?
    path("download/<uuid:pk>/", download_file_view, name="download_file"),
    path("upload/<token>/", upload_file_view, name="upload_file"),
]

# Public pages
public_page_patterns = [
    # Index or dashboard
    path(
        "",
        RedirectView.as_view(url=reverse_lazy("fs_node_browse", kwargs={"path": "/"})),
        name="index",
    ),
    path("files<path:path>", fs_node_browse_view, name="fs_node_browse"),
    path("shares", fs_node_browse_view, name="shares_dashboard"),
]

urlpatterns: list[URLPattern | URLResolver] = [
    path("admin/", admin.site.urls),
    path("", include("polyfile.apps.accounts.urls")),
    path("", include("polyfile.apps.share.urls")),
    path("", include(api_patterns)),
    path("", include(public_page_patterns)),
] + static('/docs/', document_root=settings.BASE_DIR / 'docs', view=serve_docs)

if settings.DEBUG_TOOLBAR_ENABLED:
    from debug_toolbar.toolbar import debug_toolbar_urls
    urlpatterns.extend(debug_toolbar_urls())
