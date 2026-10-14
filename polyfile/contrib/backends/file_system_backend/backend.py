import hashlib
import posixpath

from django import http
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage
from django.core.files.utils import validate_file_name
from django.db import models
from django.http import HttpRequest
from django.http.multipartparser import MultiPartParserError
from django.urls import reverse
from django.utils.timezone import now

from polyfile.apps.storage.models import FsNode
from polyfile.apps.storage.utils import get_mime_type
from polyfile.contrib.backends.base import FsBackendBase


class RawFileParser:
    def __init__(self, request: http.HttpRequest):
        """Initialize the RawFileParser object."""
        # Content-Type should not contain multipart and the boundary information.
        content_type = request.META.get("CONTENT_TYPE", "")
        if content_type.startswith("multipart/"):
            raise MultiPartParserError(f"Invalid Content-Type: {content_type}")

        # Content-Length should contain the length of the body we are about
        # to receive.
        try:
            content_length = int(request.META.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length < 0:
            # This means we shouldn't continue...raise an error.
            raise MultiPartParserError(f"Invalid content length: {content_length}")

        self._encoding = settings.DEFAULT_CHARSET
        self._content_length = content_length
        self._input_data = request
        self._chunk_size = min(x.chunk_size for x in request.upload_handlers)
        self._upload_handlers = request.upload_handlers
        self._meta = request.META

    def read(self, chunk_size: int) -> bytes | None:
        return self._input_data.read(chunk_size)


class FileSystemBackend(FileSystemStorage, FsBackendBase):
    """Stores files in a directory on the local device."""
    chunk_size = 64 * 2 ** 10  # The default chunk size is 64 KB.

    def __init__(self, location: str | None = None, upload_to: str = '', *args, **kwargs):
        if not location:
            raise ValidationError({'location': 'This field is required!'})
        self.base_location = location
        self.upload_to = upload_to
        super().__init__(*args, **kwargs)

    def download_url(self, instance: models.Model):
        return reverse('download_file', kwargs={
            'pk': instance.pk,
        })

    def save_file(self, fs_node: FsNode, request: HttpRequest) -> None:
        """Save request into file."""
        # Generate filename
        dirname = now().strftime(self.upload_to)
        filename = posixpath.join(dirname, fs_node.name)
        filename = validate_file_name(filename, allow_relative_path=True)

        # Create empty file
        fs_node.file.save(filename, ContentFile(''), save=False)
        fs_node.save(update_fields=('file', 'modified_at'))

        # File content is in request.body
        parser = RawFileParser(request=request)

        file_size = 0
        hash_md5 = hashlib.md5()
        with fs_node.file.open('wb') as file_obj:
            while chunk := parser.read(self.chunk_size):
                file_obj.write(chunk)
                hash_md5.update(chunk)
                file_size += len(chunk)

        fs_node.size = file_size
        fs_node.md5 = hash_md5.hexdigest()

        with fs_node.file.open('rb') as file_obj:
            fs_node.mime_type = get_mime_type(file_obj)

        fs_node.save(update_fields=('size', 'md5', 'mime_type'))
