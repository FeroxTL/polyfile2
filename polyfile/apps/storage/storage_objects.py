"""Value objects describing physical objects stored in a backend."""

from typing import NamedTuple


class StorageObjectRef(NamedTuple):
    """Immutable reference to one physical object: storage id plus object key.

    Some rows must outlive the ``FsNode`` they describe (archive manifests and
    the deletion outbox), so they store the pair as two plain columns. Use the
    ``storage_object`` property on those models instead of passing the columns
    around separately.
    """

    storage_id: int
    key: str
