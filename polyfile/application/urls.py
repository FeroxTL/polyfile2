from django.contrib import admin
from django.urls import include, path, reverse_lazy
from django.views.generic import RedirectView

from polyfile.accounts.views import CustomLoginView
from polyfile.application.views import files_dashboard_view
from polyfile.storage.views import download_file_view, upload_file_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(('polyfile.application.api_v1.api_v1_urls', 'api_v1')), name='api_v1'),

    # LocalDiskBackend urls todo: move to storage app? make dynamic?
    path('download/<uuid:pk>/<token>/', download_file_view, name='download_file'),
    path('upload/<token>/', upload_file_view, name='upload_file'),

    path('', RedirectView.as_view(url=reverse_lazy('files_dashboard', kwargs={'path': '/'})), name='index'),
    path('accounts/login/', CustomLoginView.as_view(), name='accounts-login'),
    path('files<path:path>', files_dashboard_view, name='files_dashboard'),
]
