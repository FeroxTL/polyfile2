# Storage backends

## Why storage backends?

Polyfile is designed to be storage-agnostic. The same logical file tree ([FsNode](models_data_model.md)) can live on different physical storage systems without changing how users interact with files. Storage backends decouple:

- **Logical structure** (directories/files represented as [FsNode](models_data_model.md)) from
- **Physical storage** (where bytes actually go - local disk, S3, FTP, etc.)

This allows configuring different storage locations per [FsStorage](models_data_model.md#fsstorage), assigning them to [users](authentication_accounts.md), and swapping implementations as needs evolve.

## How they work

### Abstraction layer
All backends inherit from `StorageBackend` in `polyfile.contrib.backends.base`. The interface is intentionally small:

- `open(name, mode="rb")` - open an existing object for reading
- `save(name, content)` - save a file-like object under `name`
- `delete(name)` - remove an object (missing objects are ignored)
- `exists(name)` - check whether an object exists
- `size(name)` - return object size in bytes
- `delete_many(names)` - bulk delete objects efficiently (default implementation loops over `delete`)
- `download_url(instance)` - generate a URL to download a file through Polyfile's controlled download flow

Backends are registered in `polyfile.apps.storage.handler.registered_backends` and selected via `FsStorage.backend`. The choices come from `get_backend_choices()`. When working with files, the backend for a node's `FsStorage` is used to read/write/delete bytes.

`FsNode.file` is a composite Python attribute backed by two database columns: `storage_id` (the selected `FsStorage`) and `object_key` (the key/path inside that storage). The real column that stores the object key is named `file` in the database for historical reasons, but the ORM field is `object_key`.

### Integration with the file tree
- **Creation**: When creating a file through the [API](../operations/api_reference.md), a [FsNode](models_data_model.md#fsnode) is created first (with metadata), then `upload_service.save_upload()` streams the uploaded content into the backend and updates the node with `size`, `md5`, and `mime_type`. Replacing an existing file reuses its node and writes the new bytes to a fresh object key.
- **Download**: The backend provides `download_url()` which typically points to Polyfile's download view (e.g., for [FileSystemBackend](#file-system-backend) it reverses to `download_file`). `serve_file()` uses `FsNode.file.open()` to stream bytes.
- **Deletion**: Physical deletion is coordinated with [recursive deletion](recursive_deletion_background_jobs.md). The deletion worker collects files to remove and calls `delete_many()` on the appropriate backend for efficient bulk removal. Backends report per-file results (`True` on success or "file not found", or an `Exception` on failure).

## File system backend

The reference implementation is `FileSystemBackend` in `polyfile.contrib.backends.file_system_backend.backend`.

### Configuration
Configured via [FsStorage.options](models_data_model.md#fsstorage). At minimum it requires `location` (the base directory on disk where files will be stored). It also supports `upload_to` for generating subdirectories (by default uses `now().strftime(self.upload_to)`, creating date-based organization).

### Upload flow
File uploads in Polyfile use a two-step flow tied to [TempUpload](models_data_model.md#tempupload):

1. **Initiate** - Client calls the API to create a file [FsNode](models_data_model.md#fsnode). A `TempUpload` is created with a token and the API returns an `upload_url`. For a replacement (`replace: true` on touch), the existing node is reused and its `TempUpload` is refreshed with a new token.

2. **Upload** - Client sends raw file bytes to that upload URL (see [API reference](../operations/api_reference.md)).

3. **Store** - `upload_service.save_upload()` reads the request body into a spooled temporary file, computes MD5 and MIME type, then calls `backend.save()` to publish the object atomically (via a temporary `.part` file and `os.replace`). It updates the `FsNode` with `size`, `md5`, and `mime_type`.

4. **Replace** - When the node already has content, the new object is written to a fresh key (the base key plus a random suffix). Only after that write succeeds does the node point at the new object and the previous key go into `PendingObjectDeletion`. The [deletion worker](recursive_deletion_background_jobs.md) removes queued objects in batches. A failed replacement therefore leaves the old file untouched, and the node's UUID, metadata and share links stay valid.

### Deletion
`FileSystemBackend.delete_many()` unlinks files directly with `os.unlink()`. It treats `FileNotFoundError` as success (idempotent) and collects other `OSError` instances as failures in the results dict.

### Download
`download_url()` generates a URL that routes through Polyfile's controlled download mechanism (`reverse('download_file', ...)`), keeping download logic centralized rather than exposing raw filesystem paths directly.

## Path handling

Path manipulation in backends and storage logic should use `pathlib.PurePosixPath` to ensure consistent forward-slash separators regardless of the host OS. This is important for cross-platform compatibility ([Security/constraints](security.md)).

## Extending with new backends

To add support for a new storage (e.g., S3, FTP):

1. **Create backend class** - Inherit from `StorageBackend`. Implement `open()`, `save()`, `delete()`, `exists()`, `size()`, `download_url()`, and override `delete_many()` if bulk operations are more efficient for that backend.

2. **Register** - Add the backend to `registered_backends` so it appears in choices.

3. **Configure** - Create an `FsStorage` instance with `backend` set to the registered key and provide backend-specific options.

4. **Test** - Ensure integration with the deletion worker and upload/download flows works correctly.

## Related docs
- [Models & data model](models_data_model.md) - FsNode, FsStorage, TempUpload
- [Recursive deletion/background jobs](recursive_deletion_background_jobs.md) - how physical deletion is coordinated
- [API reference](../operations/api_reference.md) - upload/download endpoints
- [Security](security.md) - path/filename constraints and validation
