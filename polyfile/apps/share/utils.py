import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

# Base date for time offset calculation (2020-01-01 00:00:00)
BASE_DATE = datetime(2020, 1, 1, tzinfo=UTC)


def encode_base36(num: int) -> str:
    """Encodes an integer to a Base36 string."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    if num == 0:
        return "0"
    res = ""
    while num > 0:
        num, rem = divmod(num, 36)
        res = chars[rem] + res
    return res


def decode_base36(s: str) -> int:
    """Decodes a Base36 string to an integer."""
    chars = "0123456789abcdefghijklmnopqrstuvwxyz"
    num = 0
    for char in s:
        num = num * 36 + chars.index(char)
    return num


def time_to_offset(dt: datetime) -> str:
    """Converts a datetime object to a Base36 encoded minute offset from BASE_DATE."""
    minutes = int((dt - BASE_DATE).total_seconds() // 60)
    return encode_base36(minutes)


def offset_to_time(offset_str: str) -> datetime:
    """Converts a Base36 encoded minute offset back to a datetime object."""
    minutes = decode_base36(offset_str)
    return BASE_DATE + timedelta(minutes=minutes)


def generate_download_token(share_token: str, fs_node_pk: str, expiration_time: datetime) -> str:
    """
    Generates a truncated HMAC signature for a file download.

    Args:
        share_token: The unique token of the SharedNode.
        fs_node_pk: The primary key (UUID) of the FsNode.
        expiration_time: The datetime when this link expires.

    Returns:
        A 16-character hex signature.
    """
    time_offset = time_to_offset(expiration_time)
    # Payload: share_token + fs_node_pk + time_offset
    # We use a separator to ensure the components are uniquely identifiable
    payload = f"{share_token}|{fs_node_pk}|{time_offset}"

    signature = hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    # Return truncated signature for URL compactness
    return signature[:16]


def validate_download_token(share_token: str, fs_node_pk: str, time_offset: str, signature: str) -> bool:
    """
    Validates the signature and checks if the link is expired.

    Args:
        share_token: The unique token of the SharedNode.
        fs_node_pk: The primary key (UUID) of the FsNode.
        time_offset: The Base36 encoded minute offset.
        signature: The 16-character hex signature.

    Returns:
        The fs_node_pk if the signature is valid and the link is not expired, otherwise None.
    """
    payload = f"{share_token}|{fs_node_pk}|{time_offset}"

    expected_signature = hmac.new(
        settings.SECRET_KEY.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_signature[:16]):
        return False

    return offset_to_time(time_offset) >= timezone.now()


def get_public_share_url(request: HttpRequest, share_token: str | uuid.UUID) -> str:
    """Build absolute URL of a public share root."""
    return request.build_absolute_uri(reverse("share-browse", kwargs={
        "share_token": str(share_token),
        "path": "/",
    }))


def share_download_url(share_token: str | uuid.UUID, fs_node_id: str | uuid.UUID) -> str:
    """
    Generates a download URL for a specific FsNode within a SharedNode.

    Args:
        share_token: The SharedNode.token value.
        fs_node_id: The FsNode.id value.

    Returns:
        A string containing the download URL or an empty string if inputs are missing.
    """
    share_token = str(share_token)
    fs_node_id = str(fs_node_id)
    expiration_time = timezone.now() + timedelta(hours=1)
    time_offset = time_to_offset(expiration_time)
    signature = generate_download_token(share_token, fs_node_id, expiration_time)

    return reverse("share-download", kwargs={
        "share_token": share_token,
        "fs_node_id": fs_node_id,
        "time_offset": time_offset,
        "signature": signature,
    })
