import hashlib
import io

from django import http
from django.conf import settings
from django.contrib.staticfiles.storage import StaticFilesStorage
from django.core.files.uploadedfile import UploadedFile, TemporaryUploadedFile, InMemoryUploadedFile
from django.db import models
from django.http import HttpRequest
from django.http.multipartparser import MultiPartParserError
from django.urls import reverse

from polyfile.storage.backends import BaseStorageBackend
from polyfile.storage.tokens import default_token_generator
from polyfile.storage.utils import get_mime_type


class RawFileParser:
    def __init__(self, request: http.HttpRequest):
        """Initialize the RawFileParser object."""
        # Content-Type should not contain multipart and the boundary information.
        content_type = request.META.get("CONTENT_TYPE", "")
        if content_type.startswith("multipart/"):
            raise MultiPartParserError("Invalid Content-Type: %s" % content_type)

        # Content-Length should contain the length of the body we are about
        # to receive.
        try:
            content_length = int(request.META.get("CONTENT_LENGTH", 0))
        except (ValueError, TypeError):
            content_length = 0

        if content_length < 0:
            # This means we shouldn't continue...raise an error.
            raise MultiPartParserError("Invalid content length: %r" % content_length)

        self._encoding = settings.DEFAULT_CHARSET
        self._content_length = content_length
        self._input_data = request
        self._chunk_size = min(map(lambda x: x.chunk_size, request.upload_handlers))
        self._upload_handlers = request.upload_handlers
        self._meta = request.META

    def get_file_obj(self, name: str) -> UploadedFile:
        if self._content_length <= settings.FILE_UPLOAD_MAX_MEMORY_SIZE:
            return InMemoryUploadedFile(
                file=io.BytesIO(),
                field_name=None,
                name=name,
                content_type=None,
                size=None,
                charset=None,
                content_type_extra=None,
            )
        return TemporaryUploadedFile(
            name=name,
            content_type=None,
            size=None,
            charset=None,
            content_type_extra=None,
        )


class LocalDiskBackend(StaticFilesStorage, BaseStorageBackend):
    """Stores files in a directory on the local device."""
    chunk_size = 64 * 2 ** 10  # The default chunk size is 64 KB.

    def download_url(self, instance: models.Model):
        return reverse('download_file', kwargs={
            'pk': instance.pk,
            'token': default_token_generator.make_token(instance),
        })

    def save_file(self, fs_node: models.Model, request: HttpRequest) -> None:
        parser = RawFileParser(request=request)
        file_obj = parser.get_file_obj(name=fs_node.name)

        file_size = 0
        hash_md5 = hashlib.md5()
        while chunk := request.read(self.chunk_size):
            chunk_length = len(chunk)
            hash_md5.update(chunk)
            file_obj.write(chunk)
            file_size += chunk_length

        fs_node.file = file_obj
        fs_node.size = file_obj.size = file_size
        fs_node.md5 = hash_md5.hexdigest()
        fs_node.mime_type = get_mime_type(fs_node.file)
        fs_node.save()
        file_obj.close()
