from django.conf import settings
from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView

from polyfile.apps.accounts.views import CustomLoginView
from polyfile.apps.storage.views import download_file_view, upload_file_view
from polyfile.core import api
from polyfile.core.views import files_dashboard_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("user/logout/", api.LogoutView.as_view(), name="user-logout"),
    path(
        "dashboard-context/",
        api.DashboardContextView.as_view(),
        name="dashboard_context",
    ),
    path("api/", include("polyfile.apps.storage.urls")),
    # LocalDiskBackend urls todo: move to storage app? make dynamic?
    path("download/<uuid:pk>/", download_file_view, name="download_file"),
    path("upload/<token>/", upload_file_view, name="upload_file"),
    path(
        "",
        RedirectView.as_view(url=reverse_lazy("files_dashboard", kwargs={"path": "/"})),
        name="index",
    ),
    path("accounts/login/", CustomLoginView.as_view(), name="accounts-login"),
    path("files<path:path>", files_dashboard_view, name="files_dashboard"),
]

if settings.DEBUG_TOOLBAR_ENABLED:
    from debug_toolbar.toolbar import debug_toolbar_urls
    urlpatterns += debug_toolbar_urls()
