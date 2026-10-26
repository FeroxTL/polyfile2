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

### FsNodeDeletionJob
`FsNodeDeletionJob` tracks asynchronous deletion of a subtree. It maintains status (e.g., pending/running/done/failed/timeout/cancelled), progress counters, locking information for the worker, and error details. For detailed behavior, states, and the worker algorithm, refer to [Recursive deletion/background jobs](recursive_deletion_background_jobs.md).

### TempUpload
`TempUpload` is used to handle file uploads securely. When a client initiates creating a file via the API ([API reference](../operations/api_reference.md#initiate-file-upload)), a `TempUpload` token is created tied to the newly created `FsNode` (of type file). The client then uploads the raw file content to the upload endpoint using that token. Once upload completes successfully, the upload is marked complete. This decouples file creation in the tree from the actual file transfer.

## Tree structure and path computation (CTE)

Polyfile stores the tree as an adjacency list (`FsNode.parent` pointing to another `FsNode`, or `null` for roots). To efficiently compute full paths and traverse subtrees, the codebase uses [django-cte](https://github.com/dimagi/django-cte) for Common Table Expressions.

- **Path property**: `FsNode.path` is only available when the queryset is annotated via CTE (e.g., `objects.annotate(...)`). It represents the full logical path of the node in its tree.
- **How it works**: CTEs allow recursive traversal in SQL to build paths by concatenating parent names down to roots. This avoids N+1 queries when rendering trees and enables efficient path-based lookups.
- **Usage**: APIs and services like `get_fs_node_with_children()` rely on CTE annotations to resolve paths and fetch subtrees.

## Constraints

These constraints exist to ensure cross-platform compatibility, data integrity, and security:

- **Path length < 260 characters** - Required for compatibility with Windows/NTFS filesystems. Long paths can cause issues on Windows, so keeping total paths under 260 chars prevents portability problems.
- **Filename length <= 255 characters** - Matches common filesystem limits (ext4, NTFS, etc.) and prevents truncation/compatibility issues.
- **Reserved characters forbidden** - Filenames cannot contain `< > : " / \ | ? *`. These characters are reserved or illegal on various filesystems (especially Windows), so blocking them prevents creation of unportable/unusable files.
- **URL length ~2000 bytes** - Since the API is path-based, very long URLs can hit browser/server limits. Deep nesting may need restructuring or user alerts.
- **Ownership/permission validation required** - All `FsNode` access must be validated against owner/permissions before backend operations to prevent [IDOR](security.md).
- **Tree integrity** - A directory cannot be a child of a file, and non-empty directories cannot be deleted directly (enforced by model constraints/logic). This maintains a consistent tree structure.

## Notes
- For deletion details, see [Recursive deletion/background jobs](recursive_deletion_background_jobs.md).
- For storage behavior, see [Storage backends](storage_backends.md).
- For API usage, see [API reference](../operations/api_reference.md).
