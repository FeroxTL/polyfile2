import uuid

from django.http import HttpRequest
from marshmallow import Schema, fields
from marshmallow.experimental.context import Context

from polyfile.apps.share.services import get_share_status
from polyfile.apps.share.utils import get_public_share_url, share_download_url
from polyfile.apps.storage.models import FsNode
from polyfile.apps.storage.schemas import (
    FsNodeCurrentSchema,
    FsNodeItemSchema,
)

SharedNodeTokenContext = Context[uuid.UUID]
ShareListRequestContext = Context[HttpRequest]


class ShareFsNodeItemSchema(FsNodeItemSchema):
    """FsNode list response in SharedNode schema - child items."""

    @staticmethod
    def get_download_url(obj: FsNode) -> str:
        if obj.type == FsNode.TypeChoices.FILE and obj.file:
            return share_download_url(SharedNodeTokenContext.get(), obj.pk)
        return ""


class ShareFsNodeCurrentSchema(ShareFsNodeItemSchema, FsNodeCurrentSchema):
    """FsNode list response in SharedNode schema - current item."""


class ShareFsNodeListResponseSchema(Schema):
    """FsNode list response in SharedNode schema."""
    current = fields.Nested(ShareFsNodeCurrentSchema())
    children = fields.Nested(ShareFsNodeItemSchema(), many=True)


class ShareListItemRootFsNodeSchema(Schema):
    """Minimal shared FsNode identity for the owner's share list."""
    id = fields.UUID(dump_only=True)
    name = fields.Str(dump_only=True)
    type = fields.Str(dump_only=True)
    path = fields.Method("get_path", dump_only=True, allow_none=True)

    @staticmethod
    def get_path(obj: FsNode) -> str | None:
        """Return the annotated full path without asserting it is available."""
        return getattr(obj, "_path", None)


class ShareListItemSchema(Schema):
    """One public share in the owner's share list."""
    id = fields.UUID(attribute="token", dump_only=True)
    url = fields.Method("get_url", dump_only=True, allow_none=True)
    status = fields.Method("get_status", dump_only=True)
    root_fs_node = fields.Nested(ShareListItemRootFsNodeSchema, dump_only=True)
    created_at = fields.DateTime(dump_only=True)
    expires_at = fields.DateTime(dump_only=True, allow_none=True)
    revoked_at = fields.DateTime(dump_only=True, allow_none=True)
    download_count = fields.Int(dump_only=True)
    last_downloaded_at = fields.DateTime(dump_only=True, allow_none=True)

    @staticmethod
    def get_url(obj) -> str | None:
        """Expose a public URL only while the share is usable."""
        if not obj.is_active:
            return None
        return get_public_share_url(ShareListRequestContext.get(), obj.token)

    @staticmethod
    def get_status(obj) -> str:
        """Resolve the share lifecycle status, with revocation taking priority."""
        return get_share_status(obj)


class ShareListResponseSchema(Schema):
    """Owner share list response."""
    items = fields.Nested(ShareListItemSchema(), many=True, dump_only=True)
    page = fields.Int(dump_only=True)
    page_size = fields.Int(dump_only=True)
    total = fields.Int(dump_only=True)
    has_next = fields.Bool(dump_only=True)
