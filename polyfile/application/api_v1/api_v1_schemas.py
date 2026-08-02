import typing
from pathlib import PurePosixPath

import marshmallow.types
from marshmallow import Schema, fields

from polyfile.storage.models import FsNode, FsNodeTypeChoices


class PathField(fields.Field[str]):
    """
    Adapts path to CTE queryset appropriate.

    "" -> "/"
    "/" -> "/"
    "/foo/" -> "/foo"
    "foo/" -> "/foo"
    "foo/bar" -> "/foo/bar"
    "/foo/bar" -> "/foo/bar"
    "/foo/bar/" -> "/foo/bar"
    "/foo/bar.jpg" -> "/foo/bar.jpg"
    """
    default_error_messages: marshmallow.types.ErrorMessages = {
        'invalid_utf8': 'Not a valid utf-8 string.',
    }

    def _deserialize(self, value: typing.Any, *args, **kwargs) -> PurePosixPath:
        try:
            value = fields.utils.ensure_text_type(value)
        except UnicodeDecodeError as error:
            raise self.make_error('invalid_utf8') from error

        path = PurePosixPath(value)

        if not path.is_absolute():
            # Handles relative paths ("foo/bar")
            path = PurePosixPath('/') / path

        if path.is_relative_to('//'):
            # Handles "network shared" files ("//foo/bar")
            path = PurePosixPath('/') / path.relative_to('//')

        return path


# == FsNode list ==


class FsNodeListRequestParams(typing.TypedDict):
    """Return value of FsNodeListRequestSchema().dump()."""
    path: PurePosixPath


class FsNodeListRequestSchema(Schema):
    """File list filter params."""
    # TODO: add sorting, add fields limit, add limit/offset
    path = PathField(required=True)


class FsNodeItemSchema(Schema):
    """FsNode list response - child items."""
    name = fields.Str(required=True, allow_none=False)
    type = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    modified_at = fields.DateTime(dump_only=True)
    size = fields.Int(dump_only=True)
    mime_type = fields.Str(dump_only=True)
    md5 = fields.Str(dump_only=True)
    file = fields.Str(dump_only=True)
    download_url = fields.Method('get_download_url', dump_only=True)

    @staticmethod
    def get_download_url(obj: FsNode) -> str:
        if obj.type == FsNodeTypeChoices.FILE and obj.file:
            return obj.file.download_url()
        return ''


class FsNodeCurrentSchema(FsNodeItemSchema):
    """FsNode list response - current node."""
    path = fields.Str(required=True, allow_none=False)


class FsNodeListResponseSchema(Schema):
    """FsNode list response."""
    current = fields.Nested(FsNodeCurrentSchema())
    children = fields.Nested(FsNodeItemSchema(), many=True)


# == FsNode create directory ==


class FsNodeCreateRequestSchema(Schema):
    """FsNode create params."""
    path = PathField(required=True)


def get_fs_node_name_validator() -> fields.validate.Validator:
    """Validate FsNode.name."""
    # TODO: add validation for control characters
    # TODO: add OS compatibility settings (maybe user.compat_devices)
    return fields.validate.And(
        fields.validate.Length(min=1, error='Directory name is empty'),
        fields.validate.NoneOf(('..', '.'), error='Directory name can not be "." or ".."'),
    )


# == FsNode remove ==

class FsNodeRemoveRequestSchema(Schema):
    """FsNode remove params."""
    path = PathField(required=True)
