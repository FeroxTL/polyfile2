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
    get_fs_node_with_children_by_id,
    remove_fs_node,
)
from polyfile.core import exceptions
from polyfile.core.api import BaseApiView
from polyfile.core.rest.generics import CreateApiView


class FsNodeListApiView(BaseApiView):
    @staticmethod
    def get(request: RequestType, node_id: uuid.UUID | None = None) -> http.HttpResponse:
        """Retrieve FsNode (file/directory) by UUID or path and its children (if any)."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if node_id is not None:
            fs_node_with_children = get_fs_node_with_children_by_id(
                user=request.user,
                node_id=node_id,
            )
        else:
            try:
                params = schemas.FsNodeListRequestSchema().load(request.GET)
            except marshmallow.ValidationError as e:
                raise exceptions.FieldValidationError(detail=e.messages)

            fs_node_with_children = get_fs_node_with_children(user=request.user, path=params['path'])

        with schemas.ShareUrlRequestContext(request):
            data = schemas.FsNodeListResponseSchema().dump(fs_node_with_children)
        return http.JsonResponse(data=data)

    @staticmethod
    def delete(request: RequestType, node_id: uuid.UUID | None = None) -> http.HttpResponse:
        """Remove FsNode by its UUID."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if node_id is None:
            raise exceptions.BadRequest("node_id is required")

        job = remove_fs_node(user=request.user, node_id=node_id)
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


class FsNodeCreateApiView(CreateApiView):
    """Base view for FsNode creation endpoints (directory or file)."""

    serializer_class = schemas.FsNodeCreateByNameRequestSchema
    fs_node_type: FsNode.TypeChoices

    @classmethod
    def create_node(cls, request: RequestType) -> FsNode:
        """Create an FsNode of ``fs_node_type`` from the JSON body params."""
        assert request.user.is_authenticated and isinstance(request.user, User)

        if request.user.storage_id is None:
            raise exceptions.InvalidUserStorageError(
                detail="Your storage is not configured. Contact your administrator",
            )

        params = cls.load_params(request)
        return create_fs_node(
            user=request.user,
            parent_id=params["parent_id"],
            name=params["name"],
            fs_node_type=cls.fs_node_type,
            replace=bool(params.get("replace", False)),
        )

    @classmethod
    def create(cls, request: RequestType) -> dict:
        """Create an FsNode and return its serialized item."""
        return schemas.FsNodeItemSchema().dump(cls.create_node(request))


class FsNodeMkdirApiView(FsNodeCreateApiView):
    """Create FsNode(type=directory)."""
    fs_node_type = FsNode.TypeChoices.DIRECTORY


class FsNodeTouchApiView(FsNodeCreateApiView):
    """Create or replace FsNode(type=file)."""
    serializer_class = schemas.FsNodeTouchRequestSchema
    fs_node_type = FsNode.TypeChoices.FILE

    @classmethod
    def post(cls, request: RequestType) -> http.JsonResponse:
        """Create FsNode(type=file) and start a fresh TempUpload session."""
        fs_node = cls.create_node(request)
        temp_upload, _ = TempUpload.objects.update_or_create(
            fs_node=fs_node,
            defaults={
                "token": uuid.uuid4(),
                "status": TempUpload.Status.UPLOADING,
                "completed_on": None,
            },
        )

        return cls.json_response({
            **schemas.FsNodeItemSchema().dump(fs_node),
            "upload_url": reverse("upload_file", kwargs={"token": temp_upload.token}),
        })
