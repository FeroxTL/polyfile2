import marshmallow
from django import http
from django.urls import reverse
from django_hint import RequestType

from polyfile.apps.accounts.models import User
from polyfile.apps.storage import schemas, utils
from polyfile.apps.storage.models import FsNodeTypeChoices, TempUpload
from polyfile.core import exceptions
from polyfile.core.api import BaseApiView


class FsNodeListApiView(BaseApiView):
    @staticmethod
    def get(request: RequestType) -> http.HttpResponse:
        """Retrieve FsNode (file/directory) by path and its children (if any)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        try:
            params = schemas.FsNodeListRequestSchema().load(request.GET)
        except marshmallow.ValidationError as e:
            raise exceptions.FieldValidationError(detail=e.messages)

        fs_node_with_children = utils.get_fs_node_with_children(user=request.user, path=params['path'])
        return http.JsonResponse(data=schemas.FsNodeListResponseSchema().dump(fs_node_with_children))

    @staticmethod
    def delete(request: RequestType) -> http.HttpResponse:
        """Remove FsNode."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        try:
            params = schemas.FsNodeRemoveRequestSchema().load(request.GET)
        except marshmallow.ValidationError as e:
            raise exceptions.FieldValidationError(detail=e.messages)

        utils.remove_fs_node(user=request.user, path=params['path'])
        return http.HttpResponse(status=204)


class FsNodeMkdirApiView(BaseApiView):
    @staticmethod
    def post(request: RequestType) -> http.HttpResponse:
        """Create FsNode(type=directory)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if request.user.storage_id is None:
            raise exceptions.InvalidUserStorageError(
                detail='Your storage is not configured. Contact your administrator',
            )

        params = schemas.FsNodeCreateRequestSchema().load(request.GET)
        fs_node = utils.create_fs_node(
            user=request.user,
            path=params['path'],
            fs_node_type=FsNodeTypeChoices.DIRECTORY,
        )
        return http.JsonResponse(data=schemas.FsNodeItemSchema().dump(fs_node))


class FsNodeTouchApiView(BaseApiView):
    @staticmethod
    def post(request: RequestType) -> http.HttpResponse:
        """Create FsNode(type=file)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if request.user.storage_id is None:
            raise exceptions.InvalidUserStorageError(
                detail='Your storage is not configured. Contact your administrator',
            )

        params = schemas.FsNodeCreateRequestSchema().load(request.GET)
        fs_node = utils.create_fs_node(
            user=request.user,
            path=params['path'],
            fs_node_type=FsNodeTypeChoices.FILE,
        )
        temp_upload = TempUpload.objects.create(fs_node=fs_node)

        return http.JsonResponse({
            **schemas.FsNodeItemSchema().dump(fs_node),
            'upload_url': reverse('upload_file', kwargs={'token': temp_upload.token})
        })
