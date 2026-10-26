import uuid

import marshmallow
from django import http
from django.urls import reverse
from django_hint import RequestType

from polyfile.apps.accounts.models import User
from polyfile.apps.storage import schemas
from polyfile.apps.storage.models import FsNode, FsNodeDeletionJob, TempUpload
from polyfile.apps.storage.utils import (
    create_fs_node,
    get_fs_node_with_children,
    remove_fs_node,
)
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

        fs_node_with_children = get_fs_node_with_children(user=request.user, path=params['path'])
        with schemas.ShareUrlRequestContext(request):
            data = schemas.FsNodeListResponseSchema().dump(fs_node_with_children)
        return http.JsonResponse(data=data)

    @staticmethod
    def delete(request: RequestType) -> http.HttpResponse:
        """Remove FsNode."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        try:
            params = schemas.FsNodeRemoveRequestSchema().load(request.GET)
        except marshmallow.ValidationError as e:
            raise exceptions.FieldValidationError(detail=e.messages)

        job = remove_fs_node(user=request.user, path=params['path'])
        return http.JsonResponse(
            data={"job_id": str(job.pk), "status": job.status},
            status=202,
        )


class FsNodeDeletionJobStatusApiView(BaseApiView):
    @staticmethod
    def get(request: RequestType, job_id: uuid.UUID) -> http.HttpResponse:
        assert request.user.is_authenticated and isinstance(request.user, User)
        try:
            job = FsNodeDeletionJob.objects.get(pk=job_id, owner=request.user)
        except FsNodeDeletionJob.DoesNotExist:
            raise exceptions.NotFound("Deletion job not found")
        return http.JsonResponse(
            data={
                "job_id": str(job.pk),
                "status": job.status,
                "total_nodes": job.total_nodes,
                "processed_nodes": job.processed_nodes,
                "last_error": job.last_error,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
            }
        )


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
        fs_node = create_fs_node(
            user=request.user,
            path=params['path'],
            fs_node_type=FsNode.TypeChoices.DIRECTORY,
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
        fs_node = create_fs_node(
            user=request.user,
            path=params['path'],
            fs_node_type=FsNode.TypeChoices.FILE,
        )
        temp_upload = TempUpload.objects.create(fs_node=fs_node)

        return http.JsonResponse({
            **schemas.FsNodeItemSchema().dump(fs_node),
            'upload_url': reverse('upload_file', kwargs={'token': temp_upload.token})
        })
