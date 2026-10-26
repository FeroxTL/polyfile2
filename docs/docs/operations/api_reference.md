# API reference

## Overview

The main file management APIs live in `polyfile/apps/storage/api.py`. The API is path-based and requires authentication. All file operations go through the storage/tree logic and respect [security constraints](../system_core/security.md).

## Storage API

Base paths are wired in `polyfile/core/urls.py` and `polyfile/apps/storage/urls.py`. Most endpoints are under `/api/v1/fs-node/`.

### List/get nodes
`GET /api/v1/fs-node/`

**Query params:**
- `path` (required) - Logical path to the node

**Behavior:**
Returns a recursive tree structure via [FsNode](../system_core/models_data_model.md) resolution using CTE-based path computation. The response includes the current node and its children.

**Response format:**
```json
{
  "current": {
    "name": "example.txt",
    "type": "file",
    "created_at": "2026-01-01T00:00:00Z",
    "modified_at": "2026-01-01T00:00:00Z",
    "size": 1024,
    "mime_type": "text/plain",
    "md5": "d41d8cd98f00b204e9800998ecf8427e",
    "file": "user/123/example.txt",
    "download_url": "/download/00000000-0000-0000-0000-000000000000/",
    "path": "/folder/example.txt"
  },
  "children": [
    {
      "name": "subfolder",
      "type": "directory",
      "created_at": "2026-01-01T00:00:00Z",
      "modified_at": "2026-01-01T00:00:00Z",
      "size": 0,
      "mime_type": null,
      "md5": null,
      "file": null,
      "download_url": null,
      "path": "/folder/subfolder"
    }
  ]
}
```

### Create directory
`POST /api/v1/fs-node/mkdir`

**Query params:**
- `path` (required) - Path for the new directory

**Requirements:** User must have `storage_id` configured.

**Behavior:** Creates a directory [FsNode](../system_core/models_data_model.md#fsnode) in the tree.

### Initiate file upload
`POST /api/v1/fs-node/touch`

**Query params:**
- `path` (required) - Path for the new file

**Requirements:** User must have `storage_id` configured.

**Behavior:** Creates a file [FsNode](../system_core/models_data_model.md#fsnode) and a [TempUpload](../system_core/models_data_model.md#tempupload) token. Returns node data plus `upload_url` for uploading raw content.

**Response (example):**
```json
{
  "...node_data...",
  "upload_url": "/upload/<token>/"
}
```

See [Storage backends](../system_core/storage_backends.md#upload-flow) for upload details.

### Delete node
`DELETE /api/v1/fs-node/`

**Query params:**
- `path` (required) - Path to delete

**Behavior:** Marks nodes for deletion and creates a [FsNodeDeletionJob](../system_core/models_data_model.md#fsnodedeletionjob). Returns `202 Accepted` immediately (asynchronous deletion).

**Response:**
```json
{
  "job_id": "<uuid>",
  "status": "pending"
}
```

Details in [Recursive deletion/background jobs](../system_core/recursive_deletion_background_jobs.md).

### Deletion job status
`GET /api/v1/fs-node/deletion-jobs/<uuid:job_id>/`

**Behavior:** Returns status and progress for a deletion job owned by the authenticated user.

**Response:**
```json
{
  "job_id": "...",
  "status": "pending|running|done|failed|timeout|cancelled",
  "total_nodes": 0,
  "processed_nodes": 0,
  "last_error": "...",
  "created_at": "...",
  "finished_at": "..."
}
```

## Upload & download

- **Upload**: `POST /upload/<token>/` - Upload raw file content using token from [TempUpload](../system_core/models_data_model.md#tempupload) (handled by storage views)

- **Download**: `GET /download/<uuid:pk>/` - Download file via controlled view using backend's [download_url()](../system_core/storage_backends.md#abstraction-layer)

## Other endpoints
- `GET /api/dashboard-context/` - Dashboard context
- `POST /api/v1/user/logout/` - Logout ([Authentication & accounts](../system_core/authentication_accounts.md))
- Share endpoints from `apps.share.urls` ([Sharing & signed tokens](../system_core/sharing_signed_tokens.md))

## Error handling
Uses custom exceptions from `polyfile.core.exceptions`:
- `FieldValidationError` for validation failures
- `NotFound` for missing resources
- `InvalidUserStorageError` when user has no storage configured

All errors should follow [Security](../system_core/security.md) practices (clear messages, no leaking sensitive info).

## Related docs
- [Models & data model](../system_core/models_data_model.md)
- [Storage backends](../system_core/storage_backends.md)
- [Security](../system_core/security.md)
- [Recursive deletion/background jobs](../system_core/recursive_deletion_background_jobs.md)
- [Sharing & signed tokens](../system_core/sharing_signed_tokens.md)
