"""Generic upload logic for user files.

This service is storage-backend agnostic: it resolves the backend from
``FsNode.storage_id``, builds a safe object key, streams the request body,
computes metadata and publishes the file.
"""

import hashlib
import tempfile
import uuid
from datetime import datetime
from pathlib import PurePosixPath

from django.core.files.utils import validate_file_name
from django.http import HttpRequest

from polyfile.apps.storage.handler import fs_storages
from polyfile.apps.storage.models import FsNode, PendingObjectDeletion
from polyfile.apps.storage.utils import get_mime_type

CHUNK_SIZE = 64 * 1024


def _build_object_key(fs_node: FsNode, suffix: str | None = None) -> str:
    """Build a safe, collision-free object key for the node's physical object.

    The key embeds the FsNode UUID (the node is always created before the
    upload starts) so that:
    - files with the same name uploaded on the same day never collide, even
      in different directories;
    - deleting a file and re-uploading it creates a new physical object, so a
      pending deletion of the old object can never remove the new one (the
      deletion worker deletes by object key);
    - renaming the node keeps the key valid, because the UUID never changes.

    ``suffix`` is used for replacements: writing to a fresh key keeps the old
    object intact if the upload fails, and the old key is queued for deletion
    only after the new content is safely stored.
    """
    backend = fs_storages[fs_node.storage_id]
    upload_to = getattr(backend, "upload_to", "")
    dirname = datetime.now().strftime(upload_to) if upload_to else ""
    stem = "-".join(map(str, filter(None, (fs_node.pk, suffix, fs_node.name,))))
    filename = PurePosixPath(dirname) / stem
    return str(validate_file_name(str(filename), allow_relative_path=True))


def _compute_metadata(fileobj) -> tuple[int, str, str]:
    """Return (size, md5_hex, mime_type) for a seekable file object."""
    fileobj.seek(0)
    digest = hashlib.md5()
    size = 0
    while chunk := fileobj.read(CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
    md5 = digest.hexdigest()
    fileobj.seek(0)
    mime_type = get_mime_type(fileobj)
    return size, md5, mime_type


def save_upload(fs_node: FsNode, request: HttpRequest) -> None:
    """Save a raw request body as the file content of ``fs_node``.

    A replacement writes to a new object key first. The previous object is
    queued for asynchronous deletion only after the node points to the new
    content, so a failed upload leaves the old file untouched.
    """
    backend = fs_storages[fs_node.storage_id]
    old_object_key = fs_node.object_key
    suffix = uuid.uuid4().hex[:12] if old_object_key else None
    object_key = _build_object_key(fs_node, suffix=suffix)

    # Stream into a spooled temporary file so we can compute metadata before
    # publishing the object. Small files stay in memory; large ones spill to disk.
    with tempfile.SpooledTemporaryFile(max_size=1024 * 1024, mode="w+b") as tmp:
        while chunk := request.read(CHUNK_SIZE):
            tmp.write(chunk)
        size, md5, mime_type = _compute_metadata(tmp)
        tmp.seek(0)
        backend.save(object_key, tmp)

    fs_node.object_key = object_key
    fs_node.size = size
    fs_node.md5 = md5
    fs_node.mime_type = mime_type
    fs_node.save(update_fields=("object_key", "size", "md5", "mime_type"))

    if old_object_key and old_object_key != object_key:
        PendingObjectDeletion.objects.get_or_create(
            storage_id=fs_node.storage_id,
            object_key=old_object_key,
            defaults={"node_uuid": fs_node.pk},
        )
