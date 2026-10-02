from django.urls import path

from polyfile.apps.share.views import browse_share, public_share_download

urlpatterns = [
    path("s/<uuid:share_token>/", browse_share, name="browse-share-root"),
    path("s/<uuid:share_token><path:path>", browse_share, name="browse-share"),
    path("s/download/<str:share_token>/<str:fs_node_pk>/<str:time_offset>/<str:signature>", public_share_download, name="share-download"),
]
