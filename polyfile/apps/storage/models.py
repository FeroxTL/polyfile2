import typing
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import gettext as _
from django_hint import StandardModelType

from polyfile.apps.storage import model_fields
from polyfile.apps.storage.handler import registered_backends
from polyfile.apps.storage.storage_objects import StorageObjectRef


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


class PendingObjectDeletion(models.Model, StandardModelType["PendingObjectDeletion"]):
    """Durable outbox entry for physical objects whose DB rows are already deleted."""

    storage_id = models.BigIntegerField(db_index=True)
    object_key = models.CharField(max_length=255)
    node_uuid = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        verbose_name = "Pending object deletion"
        verbose_name_plural = "Pending object deletions"
        constraints = [
            models.UniqueConstraint(
                fields=["storage_id", "object_key"],
                name="uniq_pending_object_deletion",
            ),
        ]

    def __str__(self) -> str:
        return f"PendingObjectDeletion {self.storage_id}:{self.object_key}"

    @property
    def storage_object(self) -> StorageObjectRef:
        """Return the physical object this outbox row must delete."""
        return StorageObjectRef(self.storage_id, self.object_key)


class AbstractFsNode(models.Model, StandardModelType['AbstractFsNode']):
    """Base fields for ancestors."""
    # Real DB column that stores the object key inside the selected storage.
    # Historically this column is named ``file`` in the database.
    object_key = models.CharField(
        verbose_name="Object key",
        max_length=1024,
        blank=True,
        db_column="file",
    )
    # Synthetic composite attribute backed by ``storage_id`` + ``object_key``.
    file = model_fields.FileRefField(
        storage_id_field="storage_id",
        object_key_field="object_key",
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

    storage_id: int | None
    owner_id: int | None
    _path: str | None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = None

    @property
    def storage_object(self) -> StorageObjectRef | None:
        """Return this node's physical object, or ``None`` when nothing was uploaded."""
        if self.storage_id is None or not self.object_key:
            return None
        return StorageObjectRef(self.storage_id, self.object_key)

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
        result = super().delete(using=using, keep_parents=keep_parents)
        self.file.delete()
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
    size = models.PositiveBigIntegerField(
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


class FsNodeArchiveJob(models.Model, StandardModelType["FsNodeArchiveJob"]):
    """Background job that builds a ZIP archive for a directory snapshot."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"
        CANCELLED = "cancelled", "Cancelled"

    ACTIVE_STATUSES = (Status.PENDING, Status.RUNNING, Status.READY)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archive_jobs",
    )
    root_node_uuid = models.UUIDField(db_index=True)
    root_node_name = models.CharField(max_length=255)
    fingerprint = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status,
        default=Status.PENDING,
        db_index=True,
    )
    total_files = models.PositiveIntegerField(default=0)
    total_bytes = models.PositiveBigIntegerField(default=0)
    processed_files = models.PositiveIntegerField(default=0)
    processed_bytes = models.PositiveBigIntegerField(default=0)
    archive_key = models.CharField(max_length=255, blank=True)
    archive_size = models.PositiveBigIntegerField(default=0)
    archive_md5 = models.CharField(max_length=32, blank=True)
    cancel_requested = models.BooleanField(default=False)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    locked_until = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_by = models.CharField(max_length=255, blank=True)
    scheduled_at = models.DateTimeField(default=now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reserved_bytes = models.PositiveBigIntegerField(default=0)

    class Meta:
        verbose_name = "Archive job"
        verbose_name_plural = "Archive jobs"
        constraints = [
            models.UniqueConstraint(
                fields=["root_node_uuid", "fingerprint"],
                condition=Q(status__in=("pending", "running", "ready")),
                name="uniq_active_archive_job",
            ),
        ]

    items: models.QuerySet["FsNodeArchiveItem"]

    def __str__(self) -> str:
        return f"ArchiveJob {self.pk} ({self.status})"


class FsNodeArchiveItem(models.Model, StandardModelType["FsNodeArchiveItem"]):
    """Immutable manifest entry: snapshot metadata and deletion protection for one node."""

    class EntryType(models.TextChoices):
        FILE = "file", "File"
        DIRECTORY = "directory", "Directory"

    job = models.ForeignKey(
        FsNodeArchiveJob,
        on_delete=models.CASCADE,
        related_name="items",
    )
    node = models.ForeignKey(
        FsNode,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="archive_items",
    )
    entry_type = models.CharField(max_length=16, choices=EntryType)
    zip_path = models.CharField(max_length=1024)
    # Snapshot of the physical source object: (storage_id, object_key) is copied
    # from FsNode.storage_id / FsNode.file at request time. It is not resolved
    # through the `node` FK at build time on purpose: `FsNode.file` is mutable
    # (re-upload, replace, storage migration) and PROTECT only prevents deletion.
    # An empty object_key marks a directory or a file node that was never uploaded.
    object_key = models.CharField(max_length=255, blank=True)
    storage_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    file = model_fields.FileRefField(
        storage_id_field="storage_id",
        object_key_field="object_key",
        verbose_name="File",
        blank=True,
    )
    size = models.PositiveBigIntegerField(default=0)
    md5 = models.CharField(max_length=32, blank=True)
    modified_at = models.DateTimeField(null=True, blank=True)
    position = models.PositiveIntegerField()

    class Meta:
        verbose_name = "Archive item"
        verbose_name_plural = "Archive items"
        constraints = [
            models.UniqueConstraint(
                fields=["job", "node"],
                condition=Q(node__isnull=False),
                name="uniq_archive_item_node",
            ),
            models.UniqueConstraint(
                fields=["job", "zip_path"],
                name="uniq_archive_item_zip_path",
            ),
            models.UniqueConstraint(
                fields=["job", "position"],
                name="uniq_archive_item_position",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.zip_path} ({self.entry_type})"

    @property
    def storage_object(self) -> StorageObjectRef | None:
        """Return the snapshotted source object.

        ``None`` means the entry has no physical source: a directory or a file
        node that was created but never uploaded.
        """
        if self.storage_id is None or not self.object_key:
            return None
        return StorageObjectRef(self.storage_id, self.object_key)


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
