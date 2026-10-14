import uuid
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.utils import timezone

from polyfile.apps.share.models import SharedNode
from polyfile.apps.storage.managers import get_user_fs_node_paths
from polyfile.apps.storage.models import FsNode

User = get_user_model()

SHARE_STATUS_ALL = "all"
SHARE_STATUS_ACTIVE = "active"
SHARE_STATUS_REVOKED = "revoked"
SHARE_STATUS_EXPIRED = "expired"

SHARE_STATUSES = (
    SHARE_STATUS_ALL,
    SHARE_STATUS_ACTIVE,
    SHARE_STATUS_REVOKED,
    SHARE_STATUS_EXPIRED,
)

SHARE_LIST_PAGE_SIZE = 25


def get_share_status(share: SharedNode, at: datetime | None = None) -> str:
    """
    Return the lifecycle status of a share.

    Revocation wins over expiration because it is the more explicit state:
    a revoked share that is also past its expiry date is still reported as revoked.
    """
    at = at or timezone.now()

    if share.revoked_at is not None:
        return SHARE_STATUS_REVOKED
    if share.expires_at is not None and share.expires_at <= at:
        return SHARE_STATUS_EXPIRED
    return SHARE_STATUS_ACTIVE


def _normalize_page(page: int | str | None) -> int:
    try:
        value = int(page or 1)
    except (TypeError, ValueError):
        value = 1
    return max(value, 1)


def list_user_shares(
    user: User,
    status: str = SHARE_STATUS_ALL,
    page: int | str = 1,
) -> tuple[list[SharedNode], int]:
    """
    Return one page of the current user's shares, newest first.

    The list is owner-scoped and annotated with download statistics.
    ``status`` accepts ``all``, ``active``, ``revoked`` and ``expired``.
    Uses the fixed page size ``SHARE_LIST_DEFAULT_PAGE_SIZE``.

    :argument user: The authenticated owner of the shares.
    :argument status: Optional lifecycle status filter.
    :argument page: One-based page number.

    :returns: A tuple of the annotated shares and the total matching count.

    :raises ValueError: If an unsupported status is passed.
    """
    if status not in SHARE_STATUSES:
        raise ValueError(f"Unsupported share status: {status}")

    page = _normalize_page(page)

    queryset = (
        SharedNode.objects
        .filter(owner=user)
        .select_related("root_fs_node")
        .annotate(
            download_count=Count("downloads"),
            last_downloaded_at=Max("downloads__created_at"),
        )
    )

    now = timezone.now()
    if status == SHARE_STATUS_ACTIVE:
        queryset = queryset.filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now),
            revoked_at__isnull=True,
        )
    elif status == SHARE_STATUS_REVOKED:
        queryset = queryset.filter(revoked_at__isnull=False)
    elif status == SHARE_STATUS_EXPIRED:
        queryset = queryset.filter(
            revoked_at__isnull=True,
            expires_at__isnull=False,
            expires_at__lte=now,
        )

    paginator = Paginator(queryset.order_by("-created_at"), SHARE_LIST_PAGE_SIZE)
    paginator_page = paginator.get_page(page)
    items = list(paginator_page.object_list)

    node_paths = get_user_fs_node_paths(
        user=user,
        node_ids=[item.root_fs_node_id for item in items],
    )
    for item in items:
        item.root_fs_node.path = node_paths.get(item.root_fs_node_id)

    return items, paginator.count


def create_public_share(
    user: User,
    fs_node: FsNode,
    expires_at: datetime | None = None,
) -> SharedNode:
    """
    Creates, returns, or reactivates a public share for a given FsNode.

    An active share is returned with the same token so create requests stay
    idempotent, but its expiration can be updated. A revoked or expired share is
    reactivated with a new token, so its old public URL can never be used again.

    :argument user: The authenticated user creating the share.
    :argument fs_node: The FsNode to share.
    :argument expires_at: Optional new expiration timestamp.

    :returns: The created or reactivated SharedNode object.
    """
    share, created = SharedNode.objects.get_or_create(
        root_fs_node=fs_node,
        owner=user,
        defaults={"expires_at": expires_at},
    )

    if created:
        return share

    # A revoked or expired share must never expose its old URL again.
    # Rotating the token permanently invalidates the previous public link.
    if share.revoked_at:
        share.token = uuid.uuid4()
        share.revoked_at = None
    share.expires_at = expires_at
    share.save(update_fields=["token", "revoked_at", "expires_at"])

    return share


def revoke_public_share(user: User, share_token: uuid.UUID) -> SharedNode:
    """
    Revoke a public share owned by the given user.

    Revocation is a soft delete: the share row and its download history are kept,
    but the share stops being active. A later create request rotates the token,
    so the revoked public URL can never be reused.

    :argument user: The authenticated owner of the share.
    :argument share_token: Public token of the share to revoke.

    :returns: The revoked SharedNode object.

    :raises SharedNode.DoesNotExist: If no share with this token belongs to the user.
    """
    share = SharedNode.objects.get(token=share_token, owner=user)

    if share.revoked_at is None:
        share.revoked_at = timezone.now()
        share.save(update_fields=["revoked_at"])

    return share


def hard_delete_public_share(user: User, share_token: uuid.UUID) -> None:
    """
    Permanently delete a share owned by the given user.

    Unlike revocation this removes the share row and cascades to its download
    history. It is allowed for any share lifecycle status.

    :argument user: The authenticated owner of the share.
    :argument share_token: Public token of the share to delete.

    :raises SharedNode.DoesNotExist: If no share with this token belongs to the user.
    """
    share = SharedNode.objects.get(token=share_token, owner=user)
    share.delete()
