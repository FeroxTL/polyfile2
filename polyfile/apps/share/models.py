import uuid

from django.conf import settings
from django.contrib import admin
from django.db import models
from django.db.models.query_utils import Q
from django.utils import timezone


class ActiveShareNodeManager(models.Manager):
    """
    Manager for SharedNode models to filter for active shares.

    Active shares are considered to be those that have not been revoked and 
    have either no expiration date or an expiration date in the future.
    """
    def get_queryset(self) -> models.QuerySet:
        """Return active shares."""
        return (
            super()
            .get_queryset()
            .filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
                revoked_at__isnull=True,
            )
        )


class SharedNode(models.Model):
    """Public share of FsNode."""

    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    root_fs_node = models.OneToOneField(
        "storage.FsNode",
        on_delete=models.CASCADE,
        related_name="share",
        db_index=True,
    )

    # Lifecycle
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_nodes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Shared Node"
        verbose_name_plural = "Shared Nodes"

    objects = models.Manager()
    active = ActiveShareNodeManager()

    def __str__(self):
        return f"{self.root_fs_node} ({self.token})"

    @property
    @admin.display(
        description="Active",
        boolean=True,
    )
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        return not (self.expires_at and self.expires_at <= timezone.now())


class ShareDownload(models.Model):
    """Download log — needed for limits and statistics."""

    share = models.ForeignKey(SharedNode, on_delete=models.CASCADE, related_name="downloads")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=512, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
