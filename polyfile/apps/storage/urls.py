from django.urls import path

from polyfile.apps.storage.api import (
    FsNodeListApiView,
    FsNodeMkdirApiView,
    FsNodeTouchApiView,
)

urlpatterns = [
    path('v1/fs-node/', FsNodeListApiView.as_view(), name='fs_node'),
    path('v1/fs-node/mkdir', FsNodeMkdirApiView.as_view(), name='fs_node_mkdir'),
    path('v1/fs-node/touch', FsNodeTouchApiView.as_view(), name='fs_node_touch'),
]
