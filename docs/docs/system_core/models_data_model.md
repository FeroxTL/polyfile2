# Models & data model

## Purpose of models

Polyfile's data model is built around representing a user file tree that can span different storage backends. The key idea is that files and directories are represented as entities in the database, while the actual file contents live in the configured [storage backends](storage_backends.md).

### FsStorage
`FsStorage` holds configuration for a storage backend (which backend class to use and its options). A [User](authentication_accounts.md) can be linked to a specific `FsStorage`. This allows different users/storages to be configured independently.

### FsNode
`FsNode` is the central entity representing both files and directories in the logical tree. 

- **Directories are virtual**: creating a directory does not necessarily create physical directories on disk in all backends - the tree structure is maintained in the database via parent-child relationships.
- **Files live in backends**: the actual content of files is stored by the [storage backend](storage_backends.md) (e.g., [FileSystemBackend](storage_backends.md#file-system-backend)). `FsNode` keeps metadata (name, size, mime type, md5) and a reference to the file in that backend.
- **Multi-backend capable**: different nodes can be associated with different `FsStorage` instances (via the `storage` relation), enabling flexible storage layouts.

### Deletion model
When deleting nodes, especially directories with subtrees, the system uses a tombstone approach. Nodes are marked as deleted (`deleted_at`) and assigned to a [FsNodeDeletionJob](#fsnodedeletionjob). Physical removal from backends and final cleanup from the database is handled asynchronously by the deletion worker - see [Recursive deletion/background jobs](recursive_deletion_background_jobs.md) for full details.

### Trash
Before a node is tombstoned it usually goes through the Trash. `FsNode` carries four trash fields:

- `trashed_at` - when the node was moved to the trash;
- `trash_batch_id` - the delete operation; a subtree deleted in one request shares one batch, and restoring an entry restores exactly that batch;
- `trash_purge_after` - the denormalized TTL (`POLYFILE_TRASH_TTL_DAYS`, default 30 days);
- `trash_retained_at` - the node is a directory kept only as the *path* to trashed descendants. Retained nodes are invisible both in the file manager and in the trash.

Three managers reflect the states: `FsNode.active` (visible nodes), `FsNode.trash` (restorable entries) and `FsNode.objects` (everything). The partial unique constraints require `deleted_at`, `trashed_at` and `trash_retained_at` to be `NULL`, so a trashed or retained node never blocks a same-name active sibling. Paths are never stored twice: because a trashed node stays attached to its parent, restoring it returns it to the exact path held in the tree.

### FsNodeDeletionJob
`FsNodeDeletionJob` tracks asynchronous deletion of a subtree. It maintains status (e.g., pending/running/done/failed/timeout/cancelled), progress counters, locking information for the worker, and error details. For detailed behavior, states, and the worker algorithm, refer to [Recursive deletion/background jobs](recursive_deletion_background_jobs.md).

### TempUpload
`TempUpload` is used to handle file uploads securely. When a client initiates creating a file via the API ([API reference](../operations/api_reference.md#initiate-file-upload)), a `TempUpload` token is created tied to the newly created `FsNode` (of type file). The client then uploads the raw file content to the upload endpoint using that token. Once upload completes successfully, the upload is marked complete. This decouples file creation in the tree from the actual file transfer.

A replacement (`replace: true` on touch) reuses the existing `FsNode` and refreshes its `TempUpload` with a new token and the `uploading` status, so the node keeps its UUID and share links. The previous content is queued for deletion only after the new object is stored.

### PendingObjectDeletion
`PendingObjectDeletion` is a durable outbox for physical objects whose database rows are already gone or no longer referenced. The [deletion worker](recursive_deletion_background_jobs.md) drains it in batches and records failures in `attempts` and `last_error` for retries. Entries are created when recursive deletion removes file nodes and when a replaced file switches to a fresh object key.

## Tree structure, paths and ancestors

Polyfile stores the tree as an adjacency list (`FsNode.parent` pointing to another `FsNode`, or `null` for roots). Node identity is the UUID primary key; paths are derived, never stored.

- **UUID identity**: every mutation (create/delete/share) addresses nodes by `FsNode.id` and is owner-scoped. Path segments are resolved by indexed `(owner, parent, name)` lookups (`get_fs_node_by_path_name`), one query per level.
- **Ancestor chain**: `get_fs_node_ancestors()` uses a small [django-cte](https://github.com/dimagi/django-cte) recursive CTE that walks *up* from a node to its root (O(depth)). For public shares it is clipped at the share root (`stop_at`), so ancestors never leak above the shared subtree.
- **Derived path**: a node's full logical path is built in Python from the ancestor chain (`build_fs_node_path`) when a response needs it. There is no `FsNode.path` property anymore.
- **API responses** carry `id`, `parent_id`, `ancestors` (ordered root → parent) and an optional `path` for display. The virtual root has `id: null`.

## Constraints

These constraints exist to ensure cross-platform compatibility, data integrity, and security:

- **Path length < 260 characters** - Required for compatibility with Windows/NTFS filesystems. Long paths can cause issues on Windows, so keeping total paths under 260 chars prevents portability problems.
- **Filename length <= 255 characters** - Matches common filesystem limits (ext4, NTFS, etc.) and prevents truncation/compatibility issues.
- **Reserved characters forbidden** - Filenames cannot contain `< > : " / \ | ? *`. These characters are reserved or illegal on various filesystems (especially Windows), so blocking them prevents creation of unportable/unusable files.
- **URL length ~2000 bytes** - Browser-facing read URLs are path-based, so very long URLs can hit browser/server limits. Deep nesting may need restructuring or user alerts. Mutations use UUIDs in the URL path or JSON body and are not affected.
- **Ownership/permission validation required** - All `FsNode` access must be validated against owner/permissions before backend operations to prevent [IDOR](security.md).
- **Tree integrity** - A directory cannot be a child of a file, and non-empty directories cannot be deleted directly (enforced by model constraints/logic). This maintains a consistent tree structure.

## Notes
- For deletion details, see [Recursive deletion/background jobs](recursive_deletion_background_jobs.md).
- For storage behavior, see [Storage backends](storage_backends.md).
- For API usage, see [API reference](../operations/api_reference.md).
