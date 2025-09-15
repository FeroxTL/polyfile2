import typing
from dataclasses import dataclass
from pathlib import PurePosixPath

import marshmallow
from django import http
from django.db import models

from polyfile.accounts.models import User
from polyfile.application.api_v1 import api_v1_schemas, api_v1_exceptions
from polyfile.application.api_v1.api_v1_schemas import get_fs_node_name_validator
from polyfile.storage.managers import get_user_fs_node_by_path
from polyfile.storage.models import FsNode, FsNodeTypeChoices


@dataclass
class FsNodeWithChildren:
    current: FsNode | None
    children: typing.Iterable[FsNode]


def get_fs_node_with_children(user: User, request_params: http.QueryDict) -> FsNodeWithChildren:
    """
    Retrieve FsNode (file/directory) by path and its children (if any).

    :param user: directory owner.
    :param request_params: params.
    :raises HttpException: most of the errors.
    :return FsNodeWithChildren: current FsNode and child FsNodes.
    """
    params: api_v1_schemas.FsNodeListRequestParams

    try:
        params = api_v1_schemas.FsNodeListRequestSchema().load(request_params)
    except marshmallow.ValidationError as e:
        raise api_v1_exceptions.FieldValidationError(detail=e.messages)

    try:
        fs_node: FsNode | None = get_user_fs_node_by_path(user=user, path=params['path'])
    except FsNode.DoesNotExist:
        raise api_v1_exceptions.FsNodeNotFoundError(
            detail='Can not access "%s" - no such file or directory' % params['path'],
        )

    if fs_node is None:
        # Make fs_node fake root user directory
        fs_node = FsNode(
            name='',
            type=FsNodeTypeChoices.DIRECTORY,
            storage=None,
            storage_id=None,
            owner=user,
            created_at=user.date_joined,
            modified_at=user.date_joined,
        )
        fs_node.path = ''
        # Return all root nodes
        fs_node_children = FsNode.objects.filter(owner=user, parent__isnull=True)
    elif fs_node.is_file:
        # File node can not have child nodes, so make them empty
        fs_node_children = FsNode.objects.none()
    else:
        assert fs_node.is_directory
        fs_node_children = FsNode.objects.filter(owner=user, parent=fs_node)

    fs_node_children = fs_node_children.annotate(
        sort_priority=models.Case(
            # Directories go first
            models.When(type=FsNodeTypeChoices.DIRECTORY, then=models.Value(1)),
            default=models.Value(2),
            output_field=models.IntegerField()
        )
    ).order_by('sort_priority', 'name')

    return FsNodeWithChildren(
        current=fs_node,
        children=fs_node_children,
    )


def create_fs_node(
        user: User,
        path: PurePosixPath,
        fs_node_type: FsNodeTypeChoices,
) -> FsNode:
    """
    Create FsNode.

    :param user: FSNode owner.
    :param path: target path with FSNode name included.
    :param fs_node_type: type of FSNode to be created.
    :raises HttpException: most of the errors.
    :return: created FSNode.
    """
    assert user.storage_id is not None
    base_qs: models.QuerySet[FsNode]
    parent_fs_node: FsNode | None
    parent_path = path.parent

    try:
        get_fs_node_name_validator()(path.name)
    except marshmallow.ValidationError as e:
        raise api_v1_exceptions.InvalidFsNodeName(detail=', '.join(e.messages))

    if parent_path == PurePosixPath('/'):
        base_qs, parent_fs_node = FsNode.objects, None
    else:
        base_qs = FsNode.objects.filter(parent__type=FsNodeTypeChoices.DIRECTORY)
        try:
            parent_fs_node = get_user_fs_node_by_path(user=user, path=parent_path)
        except FsNode.DoesNotExist:
            raise api_v1_exceptions.FsNodeIsNotADirectoryError(detail='Directory "%s" does not exist' % parent_path)
        if not parent_fs_node.is_directory:
            raise api_v1_exceptions.FsNodeIsNotADirectoryError(detail='"%s" is not a directory' % parent_path)

    fs_node, created = base_qs.get_or_create(
        name=path.name,
        owner=user,
        parent=parent_fs_node,
        defaults={
            'type': fs_node_type,
            'storage_id': user.storage_id,
        },
    )
    if not created:
        raise api_v1_exceptions.FsNodeExistsError(
            detail=f'{fs_node_type.name.capitalize()} named "{path.name}" already exists')
    return fs_node


def remove_fs_node(user: User, request_params: http.QueryDict) -> None:
    """
    Remove FsNode (file/directory) by path.

    Directory must be empty.

    :param user: directory owner.
    :param request_params: params.
    :raises HttpException: most of the errors.
    """
    params: api_v1_schemas.FsNodeListRequestParams

    try:
        params = api_v1_schemas.FsNodeRemoveRequestSchema().load(request_params)
    except marshmallow.ValidationError as e:
        raise api_v1_exceptions.FieldValidationError(detail=e.messages)

    try:
        fs_node: FsNode | None = get_user_fs_node_by_path(user=user, path=params['path'])
        if fs_node is None:
            raise FsNode.DoesNotExist
    except FsNode.DoesNotExist:
        raise api_v1_exceptions.FsNodeNotFoundError(
            detail='Can not access "%s" - no such file or directory' % params['path'],
        )

    if fs_node.is_file:
        # Remove FsNode(type=file)
        return fs_node.delete()

    assert fs_node.is_directory
    if not FsNode.objects.filter(owner=user, parent=fs_node).exists():
        # No descendants, can be removed safely
        return fs_node.delete()

    # TODO: implement background deletions
    #  try:
    #    fs_node.delete()
    #  except OperationalError: # has descendants
    #    return DeletionPlan()
    raise api_v1_exceptions.HttpException(detail='Not implemented yet')
