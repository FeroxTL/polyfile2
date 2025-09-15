from dataclasses import asdict

from django import http
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from polyfile.accounts.models import User
from polyfile.accounts.utils import get_sidebar_urls
from polyfile.application.api_v1 import api_v1_schemas, api_v1_exceptions, api_v1_managers
from polyfile.application.exceptions import Unauthorized, HttpException
from polyfile.storage.models import FsNodeTypeChoices, TempUpload


class BaseApiView(LoginRequiredMixin, View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *args, **kwargs):
        """Handles HttpException and returns appropriate http.JsonResponse."""
        try:
            return super().dispatch(*args, **kwargs)
        except HttpException as e:
            return http.JsonResponse(status=e.status_code, data={
                'error_id': e.error_code,
                'description': e.description,
                'detail': e.detail,
            })

    def handle_no_permission(self) -> http.HttpResponse:
        raise Unauthorized


class FsNodeListApiView(BaseApiView):
    @staticmethod
    def get(request: http.HttpRequest) -> http.HttpResponse:
        """Retrieve FsNode (file/directory) by path and its children (if any)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        fs_node_with_children = api_v1_managers.get_fs_node_with_children(user=request.user, request_params=request.GET)
        return http.JsonResponse(data=api_v1_schemas.FsNodeListResponseSchema().dump(fs_node_with_children))

    @staticmethod
    def delete(request: http.HttpRequest) -> http.HttpResponse:
        """Remove FsNode."""
        assert request.user.is_authenticated and isinstance(request.user, User)
        api_v1_managers.remove_fs_node(user=request.user, request_params=request.GET)
        return http.HttpResponse(status=204)


class FsNodeMkdirApiView(BaseApiView):
    @staticmethod
    def post(request: http.HttpRequest) -> http.HttpResponse:
        """Create FsNode(type=directory)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if request.user.storage_id is None:
            raise api_v1_exceptions.InvalidUserStorageError(
                detail='Your storage is not configured. Contact your administrator',
            )

        params = api_v1_schemas.FsNodeCreateRequestSchema().load(request.GET)
        fs_node = api_v1_managers.create_fs_node(
            user=request.user,
            path=params['path'],
            fs_node_type=FsNodeTypeChoices.DIRECTORY,
        )
        return http.JsonResponse(data=api_v1_schemas.FsNodeItemSchema().dump(fs_node))


class FsNodeTouchApiView(BaseApiView):
    @staticmethod
    def post(request: http.HttpRequest) -> http.HttpResponse:
        """Create FsNode(type=file)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if request.user.storage_id is None:
            raise api_v1_exceptions.InvalidUserStorageError(
                detail='Your storage is not configured. Contact your administrator',
            )

        params = api_v1_schemas.FsNodeCreateRequestSchema().load(request.GET)
        fs_node = api_v1_managers.create_fs_node(
            user=request.user,
            path=params['path'],
            fs_node_type=FsNodeTypeChoices.FILE,
        )
        temp_upload = TempUpload.objects.create(fs_node=fs_node)
        fs_node.upload_url = reverse('upload_file', kwargs={'token': temp_upload.token})

        return http.JsonResponse(data=api_v1_schemas.FsNodeCreateFileRequestSchema().dump(fs_node))


class DashboardContextView(BaseApiView):
    @staticmethod
    def get(request: http.HttpRequest) -> http.HttpResponse:
        return http.JsonResponse(data={
            'sidebar_urls': list(map(asdict, get_sidebar_urls(request.user)))
        })
