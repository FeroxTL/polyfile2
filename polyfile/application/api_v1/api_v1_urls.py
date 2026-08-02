from django.urls import path

from polyfile.application.api_v1 import api_v1_views

urlpatterns = [
    path('dashboard-context/', api_v1_views.DashboardContextView.as_view(), name='dashboard_context'),
    path('fs-node/', api_v1_views.FsNodeListApiView.as_view(), name='fs_node'),
    path('fs-node/mkdir', api_v1_views.FsNodeMkdirApiView.as_view(), name='fs_node_mkdir'),
    path('fs-node/touch', api_v1_views.FsNodeTouchApiView.as_view(), name='fs_node_touch'),
]
