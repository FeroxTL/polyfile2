import hashlib

import magic
from django.core.files import File


def get_md5_sum(file: File) -> str:
    """Get md5 hash of file."""
    hash_md5 = hashlib.md5()
    file.seek(0)
    for chunk in iter(lambda: file.read(4096), b""):
        hash_md5.update(chunk)
    return hash_md5.hexdigest()


def get_mime_type(file: File) -> str:
    """Get mimetype of file."""
    file.seek(0)
    return magic.from_buffer(file.read(2048), mime=True)
