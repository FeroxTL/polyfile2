import datetime
import hashlib
import time
import typing
import uuid
from datetime import timedelta

from django.conf import settings
from django.core import exceptions
from django.core.files.uploadedfile import UploadedFile
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext as _

from polyfile.storage import model_fields
from polyfile.storage.handler import registered_backends


def get_backend_list() -> dict[str, str]:
    return registered_backends


class Storage(models.Model):
    """Storage config."""
    name: str = models.CharField(
        verbose_name="Name",
        max_length=32,
    )
    backend: str = models.CharField(
        max_length=255,
        verbose_name="Backend",
        choices=get_backend_list,
    )
    options: dict = models.JSONField(
        default=dict,
        verbose_name="Options",
        blank=True, null=False,
    )

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.pk}>"

    def __str__(self) -> str:
        return self.name


class AbstractFsNode(models.Model):
    """Base fields for ancestors."""
    file: model_fields.FsStorageFieldFile | None = model_fields.FsStorageFileField(
        verbose_name="File",
        blank=True,
    )
    storage: Storage = models.ForeignKey(
        Storage,
        verbose_name="Storage",
        on_delete=models.PROTECT,
    )
    owner: models.Model = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        verbose_name="Owner",
        on_delete=models.PROTECT,
    )
    mime_type: str = models.CharField(
        verbose_name="Mimetype",
        max_length=256,
        blank=True,
        editable=False,
    )
    md5: str = models.CharField(
        verbose_name="md5",
        max_length=16,
        blank=True,
        editable=False,
    )
    modified_at: datetime.datetime = models.DateTimeField(
        verbose_name="Date update",
        auto_now=True,
    )

    class Meta:
        abstract = True

    DoesNotExist: typing.Type[models.ObjectDoesNotExist]
    storage_id: str | None
    owner_id: int | None
    _path: str | None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = None

    @property
    def path(self) -> str:
        """Full path in Storage."""
        assert self._path is not None, (
            f"No \"path\" attribute was provided using annotations "
            f"({self.__class__.__name__}.objects.annotate(...)) or direct assignments."
        )
        return self._path

    @path.setter
    def path(self, value: str) -> None:
        self._path = value

    def delete(self, using=None, keep_parents=False) -> None:
        """Delete associated file while deleting node instance."""
        super().delete(using=using, keep_parents=keep_parents)
        self.file.delete(save=False)


class FsNodeTypeChoices(models.TextChoices):
    DIRECTORY = "directory", "Directory"
    FILE = "file", "File"


class FsNode(AbstractFsNode):
    """File or directory node."""
    id: uuid.UUID | None = models.UUIDField(primary_key=True, db_index=True, default=uuid.uuid4, blank=True)
    # TODO: check if CompositeKey(uuid4+user_id) can be primary key

    name: str = models.CharField(
        verbose_name="Name",
        max_length=255,
        db_index=True,
        blank=False, null=False,
    )
    size: int = models.PositiveIntegerField(
        verbose_name="Size",
        default=0,
        help_text="Size in bytes",
        editable=False,
    )

    type: str = models.CharField(
        verbose_name="Node type",
        max_length=16,
        db_index=True,
        choices=FsNodeTypeChoices,
    )
    parent: typing.Self = models.ForeignKey(
        "self",
        related_name="children_set",
        # blank and null means parent is root directory
        blank=True,
        null=True,
        db_index=True,
        # Can not delete non-empty directory
        on_delete=models.PROTECT,
        # Can not create directory in file (not a database constraint, should be validated with `FsNode.clean_fields()`)
        limit_choices_to={"type": FsNodeTypeChoices.DIRECTORY},
    )
    created_at: datetime.datetime = models.DateTimeField(
        verbose_name="Creation date",
        auto_now_add=True,
    )

    class Meta:
        verbose_name = "Node"
        verbose_name_plural = "Nodes"
        unique_together = [
            ("name", "parent", "storage"),
        ]

    get_type_display: typing.Callable
    objects = models.Manager()

    def __str__(self) -> str:
        return f'{self.get_type_display()} "{self.name}"'

    @property
    def is_directory(self) -> bool:
        """Check if node is directory."""
        return self.type == FsNodeTypeChoices.DIRECTORY

    @property
    def is_file(self) -> bool:
        """Check if node is file."""
        return self.type == FsNodeTypeChoices.FILE

    def clean(self):
        super().clean()

        if self.is_directory:
            self.file = None
        elif self.is_file and not self.file:
            raise exceptions.ValidationError({
                "file": "Required",  # TODO: specify error text
            })


class ChunkedStatus(models.IntegerChoices):
    UPLOADING = 1, _("Uploading")
    COMPLETE = 2, _("Complete")


class TempUpload(models.Model):
    token = models.UUIDField(max_length=32, unique=True, editable=False, default=uuid.uuid4)

    fs_node = models.OneToOneField(
        FsNode,
        limit_choices_to={
            'type': FsNodeTypeChoices.FILE,
        },
        on_delete=models.CASCADE,
    )

    status = models.PositiveSmallIntegerField(choices=ChunkedStatus, default=ChunkedStatus.UPLOADING)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_on = models.DateTimeField(null=True, blank=True)
