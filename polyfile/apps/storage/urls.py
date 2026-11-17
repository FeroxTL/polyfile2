from django.urls import path

from polyfile.apps.storage.api import (
    FsNodeDeletionJobStatusApiView,
    FsNodeListApiView,
    FsNodeMkdirApiView,
    FsNodeTouchApiView,
    TrashEmptyApiView,
    TrashEntryApiView,
    TrashEntryRestoreApiView,
    TrashListApiView,
)

urlpatterns = [
    # Nodes
    path('v1/fs-node/', FsNodeListApiView.as_view(), name='fs_node'),
    path('v1/fs-node/<uuid:node_id>/', FsNodeListApiView.as_view(), name='fs_node_by_id'),
    path('v1/fs-node/mkdir', FsNodeMkdirApiView.as_view(), name='fs_node_mkdir'),
    path('v1/fs-node/touch', FsNodeTouchApiView.as_view(), name='fs_node_touch'),
    path('v1/fs-node/deletion-jobs/<uuid:job_id>/', FsNodeDeletionJobStatusApiView.as_view(), name='fs_node_deletion_job'),
    # Trash
    path('v1/trash/', TrashListApiView.as_view(), name='trash_list'),
    path('v1/trash/empty', TrashEmptyApiView.as_view(), name='trash_empty'),
    path('v1/trash/<uuid:entry_id>/', TrashEntryApiView.as_view(), name='trash_entry'),
    path('v1/trash/<uuid:entry_id>/restore', TrashEntryRestoreApiView.as_view(), name='trash_entry_restore'),
]
