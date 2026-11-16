import typing
from pathlib import PurePosixPath

import marshmallow.types
from django.core.exceptions import ObjectDoesNotExist
from django.http.request import HttpRequest
from django.urls import reverse
from marshmallow import Schema, fields, validate
from marshmallow.experimental.context import Context

from polyfile.apps.share.models import SharedNode
from polyfile.apps.share.utils import get_public_share_url
from polyfile.apps.storage.models import FsNode

# Request is required to build absolute public share URLs.
ShareUrlRequestContext = Context[object]


def ensure_absolute_path(value: str | bytes) -> PurePosixPath:
    """
    Adapts path to CTE queryset appropriate.

    "" -> "/"
    "/" -> "/"
    "/foo/" -> "/foo"
    "foo/" -> "/foo"
    "foo/bar" -> "/foo/bar"
    "/foo/bar" -> "/foo/bar"
    "/foo/bar/" -> "/foo/bar"
    "//foo/bar/" -> "/foo/bar"
    "/foo/bar.jpg" -> "/foo/bar.jpg"

    :raises UnicodeDecodeError: If path can not be decoded.
    """
    path = PurePosixPath(fields.utils.ensure_text_type(value))

    if not path.is_absolute():
        # Handles relative paths ("foo/bar")
        path = PurePosixPath("/") / path

    if path.is_relative_to("//"):
        # Handles "network shared" files ("//foo/bar")
        path = PurePosixPath("/") / path.relative_to("//")

    return path


class PathField(fields.Field[str]):
    """Uses `ensure_absolute_path` for path validation."""
    default_error_messages: marshmallow.types.ErrorMessages = {
        'invalid_utf8': 'Not a valid utf-8 string.',
    }

    def _deserialize(self, value: typing.Any, *args, **kwargs) -> PurePosixPath:
        try:
            return ensure_absolute_path(value)
        except UnicodeDecodeError as error:
            raise self.make_error('invalid_utf8') from error


# == FsNode list ==


class FsNodeListRequestParams(typing.TypedDict):
    """Return value of FsNodeListRequestSchema().dump()."""
    path: PurePosixPath


class FsNodeListRequestSchema(Schema):
    """File list filter params."""
    # TODO: add sorting, add fields limit, add limit/offset
    path = PathField(required=False, load_default=PurePosixPath('/'))


class FsNodeItemSchema(Schema):
    """FsNode list response - child items."""
    id = fields.UUID(dump_only=True, allow_none=True)
    parent_id = fields.UUID(dump_only=True, allow_none=True)
    name = fields.Str(required=True, allow_none=False)
    type = fields.Str(dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    modified_at = fields.DateTime(dump_only=True)
    size = fields.Int(dump_only=True)
    mime_type = fields.Str(dump_only=True)
    md5 = fields.Str(dump_only=True)
    file = fields.Method("get_file", dump_only=True)
    download_url = fields.Method('get_download_url', dump_only=True)

    @staticmethod
    def get_file(obj: FsNode) -> str:
        return obj.object_key or ""

    @staticmethod
    def get_download_url(obj: FsNode) -> str:
        if obj.is_file and obj.file:
            return obj.file.download_url()
        # The virtual "/" root is an unsaved FsNode, so it has no archive.
        if obj.is_directory and obj.pk and not obj._state.adding:
            # Directories are always archived asynchronously, so the URL
            # starts an archive job instead of streaming a file.
            return reverse("download_file", kwargs={"pk": obj.pk})
        return ""

    @staticmethod
    def get_share(obj: FsNode) -> dict[str, str | None] | None:
        """Return public share info for an active share, if any."""
        request = ShareUrlRequestContext.get(None)
        if request is None or not obj.pk:
            return None
        assert isinstance(request, HttpRequest)

        try:
            share: SharedNode = obj.share
        except ObjectDoesNotExist:
            return None

        # TODO: convert to nested schema
        return {
            "id": str(share.token),
            "url": get_public_share_url(request, share.token),
            "expires_at": share.expires_at.isoformat() if share.expires_at else None,
            "revoked_at": share.revoked_at.isoformat() if share.revoked_at else None,
        }


class FsNodeItemWithShareSchema(FsNodeItemSchema):
    """FsNode list response item with public share info."""
    share = fields.Method("get_share", dump_only=True, allow_none=True)


class FsNodeCurrentSchema(FsNodeItemSchema):
    """FsNode list response - current node."""


class FsNodeCurrentWithShareSchema(FsNodeCurrentSchema):
    """FsNode list response current node with public share info."""
    share = fields.Method("get_share", dump_only=True, allow_none=True)


class FsNodeAncestorSchema(Schema):
    """FsNode list response - ancestor breadcrumb item."""
    id = fields.UUID(dump_only=True)
    name = fields.Str(dump_only=True)


class FsNodeListResponseSchema(Schema):
    """FsNode list response."""
    current = fields.Nested(FsNodeCurrentWithShareSchema())
    ancestors = fields.Nested(FsNodeAncestorSchema(), many=True, dump_only=True)
    children = fields.Nested(FsNodeItemWithShareSchema(), many=True)


# == FsNode create ==


# Cross-platform reserved characters (Windows/NTFS compatible), see AGENTS.md.
RESERVED_NAME_CHARACTERS = frozenset('<>:"/\\|?*')


def _validate_name_characters(value: str) -> None:
    """Reject names with characters that are unsafe across supported platforms."""
    bad = RESERVED_NAME_CHARACTERS.intersection(value)
    if bad:
        raise marshmallow.ValidationError(
            f'Name contains reserved characters: {" ".join(sorted(bad))}',
        )


def get_fs_node_name_validator() -> fields.validate.Validator:
    """Validate FsNode.name."""
    # TODO: add validation for control characters
    # TODO: add OS compatibility settings (maybe user.compat_devices)
    return validate.And(
        validate.Length(min=1, error='Directory name is empty'),
        validate.Length(max=255, error='Name is too long (255 characters max)'),
        validate.NoneOf(('..', '.'), error='Directory name can not be "." or ".."'),
        _validate_name_characters,
    )


class FsNodeCreateByNameRequestSchema(Schema):
    """FsNode create params (UUID identity): parent UUID + name."""
    parent_id = fields.UUID(required=False, allow_none=True, load_default=None)
    name = fields.Str(required=True, validate=get_fs_node_name_validator())


class FsNodeTouchRequestSchema(FsNodeCreateByNameRequestSchema):
    """File upload session params: create or replace an existing file node."""
    replace = fields.Bool(load_default=False)
