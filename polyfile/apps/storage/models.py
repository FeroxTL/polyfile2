import typing
import uuid

from django.conf import settings
from django.core import exceptions
from django.db import models
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_hint import StandardModelType

from polyfile.apps.storage import model_fields
from polyfile.apps.storage.handler import registered_backends


def get_backend_choices() -> dict[str, str]:
    return {
        key: cls.name or cls.__name__
        for key, cls in registered_backends.items()
    }


class FsStorage(models.Model, StandardModelType['FsStorage']):
    """Storage config."""
    name = models.CharField(
        verbose_name="Name",
        max_length=32,
    )
    backend = models.CharField(
        max_length=255,
        verbose_name="Backend",
        choices=get_backend_choices,
    )
    options = models.JSONField(
        default=dict,
        verbose_name="Options",
        blank=True, null=False,
    )

    class Meta:
        verbose_name = 'Storage'
        verbose_name_plural = 'Storages'

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.pk}>"

    def __str__(self) -> str:
        return self.name


class FsNodeDeletionJob(models.Model, StandardModelType['FsNodeDeletionJob']):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        TIMEOUT = "timeout", "Timeout"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    root_path = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.PENDING, db_index=True)
    total_nodes = models.PositiveIntegerField(default=0)
    processed_nodes = models.PositiveIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    scheduled_at = models.DateTimeField(default=now, db_index=True)
    locked_until = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_by = models.CharField(max_length=255, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Node deletion job"
        verbose_name_plural = "Node deletion jobs"

    def __str__(self) -> str:
        return f"DeletionJob {self.pk} ({self.status})"


class AbstractFsNode(models.Model, StandardModelType['AbstractFsNode']):
    """Base fields for ancestors."""
    file = model_fields.FsStorageFileField(
        verbose_name="File",
        blank=True,
    )
    storage = models.ForeignKey(
        FsStorage,
        verbose_name="Storage",
        on_delete=models.PROTECT,
    )
    owner = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        verbose_name="Owner",
        on_delete=models.PROTECT,
    )
    mime_type = models.CharField(
        verbose_name="Mimetype",
        max_length=256,
        blank=True,
        editable=False,
    )
    md5 = models.CharField(
        verbose_name="md5",
        max_length=32,
        blank=True,
        editable=False,
    )
    modified_at = models.DateTimeField(
        verbose_name="Date update",
        auto_now=True,
    )

    class Meta:
        abstract = True

    storage_id: str | None
    owner_id: int | None
    _path: str | None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = None

    @property
    def path(self) -> str:
        """
        Full path in Storage.

        This property is only available in CTE selections (when query is annotated).
        """
        assert self._path is not None, (
            f"No \"path\" attribute was provided using annotations "
            f"({self.__class__.__name__}.objects.annotate(...)) or direct assignments."
        )
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = value

    def delete(self, using=None, keep_parents=False) -> tuple[int, dict[str, int]]:
        """Delete associated file while deleting node instance."""
        # todo: post_delete
        result = super().delete(using=using, keep_parents=keep_parents)
        self.file.delete(save=False)
        return result


class ActiveFsNodeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class FsNode(AbstractFsNode):
    """File or directory node."""
    id = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4, blank=True)
    # TODO: check if CompositeKey(uuid4+user_id) can be primary key

    class TypeChoices(models.TextChoices):
        DIRECTORY = "directory", "Directory"
        FILE = "file", "File"

    name = models.CharField(
        verbose_name="Name",
        max_length=255,
        db_index=True,
        blank=False, null=False,
    )
    size = models.PositiveIntegerField(
        verbose_name="Size",
        default=0,
        help_text="Size in bytes",
        editable=False,
    )

    type = models.CharField(
        verbose_name="Node type",
        max_length=16,
        db_index=True,
        choices=TypeChoices,
    )
    parent = models.ForeignKey(
        "self",
        related_name="children_set",
        # blank and null means parent is root directory
        blank=True,
        null=True,
        db_index=True,
        # Can not delete non-empty directory
        on_delete=models.PROTECT,
        # Can not create directory in file (not a database constraint, should be validated with `FsNode.clean_fields()`)
        limit_choices_to={"type": TypeChoices.DIRECTORY},
    )
    created_at = models.DateTimeField(
        verbose_name="Creation date",
        auto_now_add=True,
    )

    # deleted_at + FsNodeDeletionJob is a tombstone for background cleanup, not a recycle bin
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_job = models.ForeignKey(
        FsNodeDeletionJob,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="nodes",
        db_index=True,
    )

    objects = models.Manager()
    active = ActiveFsNodeManager()

    class Meta:
        verbose_name = "Node"
        verbose_name_plural = "Nodes"
        constraints = [
            # Unique constraint for non-root nodes: active nodes must have unique names
            #  within the same parent and storage. Tombstones may have duplicate names.
            models.UniqueConstraint(
                fields=["name", "parent", "storage"],
                condition=Q(deleted_at__isnull=True),
                name="uniq_active_name_parent_storage",
            ),
            # Unique constraint for root nodes (parent is null):
            #  active root nodes must have unique names within the same storage.
            # Default SQL behavior (parent=NULL) allows to have duplicates.
            models.UniqueConstraint(
                fields=["name", "storage", "owner"],
                condition=Q(parent__isnull=True, deleted_at__isnull=True),
                name="uniq_active_root_name_storage",
            ),
        ]

    get_type_display: typing.Callable

    def __str__(self) -> str:
        return f'{self.get_type_display()} "{self.name}"'

    @property
    def is_directory(self) -> bool:
        """Check if node is directory."""
        return self.type == self.TypeChoices.DIRECTORY

    @property
    def is_file(self) -> bool:
        """Check if node is file."""
        return self.type == self.TypeChoices.FILE

    def clean(self):
        super().clean()

        if self.is_directory:
            self.file = None
        elif self.is_file and not self.file:
            raise exceptions.ValidationError({
                "file": "Required",  # TODO: specify error text
            })


class TempUpload(models.Model, StandardModelType['TempUpload']):
    """Public link for upload."""

    class Status(models.IntegerChoices):
        UPLOADING = 1, _("Uploading")
        COMPLETE = 2, _("Complete")
    
    token = models.UUIDField(max_length=32, unique=True, editable=False, default=uuid.uuid4)

    fs_node = models.OneToOneField(
        FsNode,
        limit_choices_to={
            'type': FsNode.TypeChoices.FILE,
        },
        on_delete=models.CASCADE,
    )

    status = models.PositiveSmallIntegerField(choices=Status, default=Status.UPLOADING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_on = models.DateTimeField(null=True, blank=True)

    def mark_complete(self) -> None:
        """Mart as complete."""
        self.status = self.Status.COMPLETE
        self.completed_on = now()
        self.save(update_fields=('status', 'completed_on'))
