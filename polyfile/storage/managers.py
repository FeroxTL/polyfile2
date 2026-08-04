from functools import partial
from pathlib import PurePosixPath

from django.contrib.auth.base_user import AbstractBaseUser
from django.db import models
from django.db.models.functions import Concat
from django_cte import CTE, with_cte

from polyfile.storage.models import FsNode


def make_fs_node_cte(cte: CTE, base_queryset: models.QuerySet):
    """Queryset for instance of recursive CTE."""
    # non-recursive: get root nodes
    return base_queryset.filter(
        parent__isnull=True,
    ).values(
        'id',
        path=Concat(models.Value('/'), models.F('name')),
    ).union(
        # recursive union: get descendants
        cte.join(base_queryset.model, parent_id=cte.col.id).values(
            'id',
            path=Concat(
                cte.col.path, models.Value('/'), models.F('name'),
                output_field=models.TextField(),
            ),
        ),
        all=False,
    )


def get_user_fs_node_by_path(user: AbstractBaseUser, path: PurePosixPath) -> FsNode | None:
    """
    Get FsNode with owner=user and path=path.

    :raises FsNode.DoesNotExist: If FsNode with specified path does not exist.
    """
    if path != PurePosixPath('/'):
        cte = CTE.recursive(partial(make_fs_node_cte, base_queryset=FsNode.objects.filter(owner=user)))
        return with_cte(
            cte,
            select=cte.join(FsNode, id=cte.col.id)
            .annotate(path=cte.col.path)
            .filter(path=path, owner=user)
        ).get()
    return None
