from django.urls import path
from django.views.generic.base import TemplateView

from polyfile.apps.share.views import (
    CreateShareView,
    GetShareDetailApiView,
    ListSharesApiView,
    PermanentDeleteShareView,
    RevokeShareView,
    public_share_download,
)

urlpatterns = [
    # Public pages
    path(
        "s/<uuid:share_token><path:path>",  # "path" can be empty or include slash symbol
        TemplateView.as_view(template_name="share/public_share.html"),
        name="share-browse",
    ),
    path(
        "s/download/<str:share_token>/<str:fs_node_id>/<str:time_offset>/<str:signature>",
        public_share_download,
        name="share-download",
    ),
    # Api pages
    path(
        "api/shares/",
        ListSharesApiView.as_view(),
        name="share-list",
    ),
    path(
        "api/shares/create<path:path>",
        CreateShareView.as_view(),
        name="share-create",
    ),
    path(
        "api/shares/<uuid:share_token>/delete",
        PermanentDeleteShareView.as_view(),
        name="share-permanent-delete",
    ),
    path(
        "api/shares/<uuid:share_token>/revoke",
        RevokeShareView.as_view(),
        name="share-api-revoke",
    ),
    path(
        "api/shares/detail/<uuid:share_token><path:path>", # "path" can be empty or include slash symbol
        GetShareDetailApiView.as_view(),
        name="share-api-detail-path",
    ),
]
