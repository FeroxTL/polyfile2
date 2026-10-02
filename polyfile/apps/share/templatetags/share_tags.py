from datetime import timedelta
from uuid import UUID

from django.template.defaulttags import register
from django.urls import reverse
from django.utils import timezone

from polyfile.apps.share.utils import generate_download_token, time_to_offset


@register.simple_tag
def share_download_url(share_token: str | UUID, fs_node_pk: str | UUID) -> str:
    """
    Generates a download URL for a specific node within a share.

    Args:
        share_token: The SharedNode.token value.
        fs_node_pk: The FsNode.id value.

    Returns:
        A string containing the download URL or an empty string if inputs are missing.
    """
    share_token = str(share_token)
    fs_node_pk = str(fs_node_pk)
    expiration_time = timezone.now() + timedelta(hours=1)
    time_offset = time_to_offset(expiration_time)
    signature = generate_download_token(share_token, fs_node_pk, expiration_time)

    return reverse("share-download", kwargs={
        "share_token": share_token,
        "fs_node_pk": fs_node_pk,
        "time_offset": time_offset,
        "signature": signature
    })
