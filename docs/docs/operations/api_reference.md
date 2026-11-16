# API reference

## Overview

The main file management APIs live in `polyfile/apps/storage/api.py`. Read operations are path- or UUID-based; all mutations (create, delete, share) address nodes by their UUID (`FsNode.id`). All file operations go through the storage/tree logic and respect [security constraints](../system_core/security.md).

## Storage API

Base paths are wired in `polyfile/core/urls.py` and `polyfile/apps/storage/urls.py`. Most endpoints are under `/api/v1/fs-node/`.

### List/get nodes
`GET /api/v1/fs-node/` or `GET /api/v1/fs-node/<uuid:node_id>/`

**Query params (path-based form only):**
- `path` (optional, defaults to `/`) - Logical path to the node

**Behavior:**
Returns the current node, its ancestors (breadcrumb chain, root first) and its children. UUID lookups are owner-scoped: a foreign, deleted or unknown UUID returns 404. For the virtual root (`path=/` or no `node_id`), `current.id` is `null` and `ancestors` is empty.

**Response format:**
```json
{
  "current": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "parent_id": "6a2e8400-e29b-41d4-a716-446655440001",
    "name": "example.txt",
    "type": "file",
    "created_at": "2026-01-01T00:00:00Z",
    "modified_at": "2026-01-01T00:00:00Z",
    "size": 1024,
    "mime_type": "text/plain",
    "md5": "d41d8cd98f00b204e9800998ecf8427e",
    "file": "user/123/example.txt",
    "download_url": "/download/550e8400-e29b-41d4-a716-446655440000/",
    "path": "/folder/example.txt"
  },
  "ancestors": [
    {"id": "6a2e8400-e29b-41d4-a716-446655440001", "name": "folder"}
  ],
  "children": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "parent_id": "550e8400-e29b-41d4-a716-446655440000",
      "name": "subfolder",
      "type": "directory"
    }
  ]
}
```

### Create directory
`POST /api/v1/fs-node/mkdir`

**JSON body:**
- `name` (required) - Directory name (reserved characters `< > : " / \ | ? *` are rejected)
- `parent_id` (optional, default `null`) - UUID of the parent directory; `null` creates in the virtual root

**Requirements:** User must have `storage_id` configured.

**Behavior:** Creates a directory [FsNode](../system_core/models_data_model.md#fsnode) in the tree. A foreign or missing `parent_id` returns 404; a file parent returns 409; a duplicate name returns 409.

### Initiate file upload
`POST /api/v1/fs-node/touch`

**JSON body:**
- `name` (required) - File name
- `parent_id` (optional, default `null`) - UUID of the parent directory
- `replace` (optional, default `false`) - Reuse an existing file with the same name
  instead of returning `409`

**Requirements:** User must have `storage_id` configured.

**Behavior:** Creates a file [FsNode](../system_core/models_data_model.md#fsnode) and a
[TempUpload](../system_core/models_data_model.md#tempupload) token. Returns node data plus
`upload_url` for uploading raw content. Every call issues a fresh `TempUpload` token in the
`uploading` state, including when an existing file is replaced.

With `replace: true` an existing file with the same name is reused: its `id`, `parent_id`,
`share` and other node metadata are preserved, and the upload writes new content. Directories
can never be replaced. If the name belongs to a directory, the request still returns `409`.

**Response (example):**
```json
{
  "id": "11111111-1111-1111-1111-111111111111",
  "parent_id": "6a2e8400-e29b-41d4-a716-446655440001",
  "name": "report.pdf",
  "upload_url": "/upload/<token>/"
}
```

**Conflict response:** When the name is taken and `replace` is not set, the error carries
the existing node so a client can offer replacement:

```json
{
  "error_id": "FsNodeExistsError",
  "description": "Target object already exists.",
  "detail": "File named \"report.pdf\" already exists",
  "existing_node_id": "6a2e8400-e29b-41d4-a716-446655440001",
  "existing_type": "file"
}
```

`existing_type` is `file` or `directory`; only files can be replaced.

See [Storage backends](../system_core/storage_backends.md#upload-flow) for upload details.

### Delete node
`DELETE /api/v1/fs-node/<uuid:node_id>/`

**Behavior:** Marks the node's subtree for deletion and creates a [FsNodeDeletionJob](../system_core/models_data_model.md#fsnodedeletionjob). Returns `202 Accepted` immediately (asynchronous deletion). Foreign, deleted or unknown UUIDs return 404.

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

## Share API

- `POST /api/shares/` with JSON body `{"node_id": "<uuid>", "expires_at": "<iso datetime>|null"}` - create or reactivate a public share for the node (owner-scoped; foreign or unknown nodes return 404).
- `GET /api/shares/` - list the current user's shares (`status`, `page` query params).
- `POST /api/shares/<uuid:share_token>/revoke` - revoke a share (soft delete).
- `DELETE /api/shares/<uuid:share_token>/delete` - permanently delete a share.
- `GET /api/shares/detail/<uuid:share_token>/<path>/` - public read inside a share; `ancestors` never climb above the share root and the share root's `parent_id` is hidden.

See [Sharing & signed tokens](../system_core/sharing_signed_tokens.md) for the full model.

## Upload & download

- **Upload**: `POST /upload/<token>/` - Upload raw file content using token from
  [TempUpload](../system_core/models_data_model.md#tempupload) (handled by storage views).
  The node may already have content when a file is being replaced; the new bytes are stored
  under a fresh object key and the old object is queued for deletion.

- **Download**: `GET /download/<uuid:pk>/` - Download file via controlled view using backend's [download_url()](../system_core/storage_backends.md#abstraction-layer)

### Directory archives

Directories are always downloaded asynchronously:

- `GET /download/<uuid:pk>/` - browser request; responds with `303 See Other` to the waiting page.
- `GET /download/<uuid:pk>/?format=json` - API request; responds with `202 Accepted`, a job id and `Retry-After`.
- `GET /download/jobs/<job_id>/` - HTML waiting page with polling.
- `GET /download/jobs/<job_id>/status/` - JSON job state, progress and `file_url` when ready.
- `GET /download/jobs/<job_id>/file/` - the ready ZIP archive (`202` while building, `410` when unavailable).
- `HEAD /download/jobs/<job_id>/file/` - availability preflight without streaming the ZIP; returns the same `200`/`202`/`410` status codes.

The `download_url` field in the file list points to the first endpoint for both files and directories.
The SPA uses `?format=json` and polls the status URL from the waiting modal. Before navigating to
`file_url`, it sends a `HEAD` request so a deleted or expired archive is reported inside the modal
instead of opening the JSON error response as a new page.

## Other endpoints
- `GET /api/dashboard-context/` - Dashboard context
- `POST /api/v1/user/logout/` - Logout ([Authentication & accounts](../system_core/authentication_accounts.md))

## Error handling
Uses custom exceptions from `polyfile.core.exceptions`:
- `FieldValidationError` for validation failures
- `BadRequest` for malformed JSON bodies
- `NotFound` for missing resources
- `InvalidUserStorageError` when user has no storage configured

Errors share a common JSON shape. Exceptions may add extra fields, which are merged into
the response body:

```json
{
  "error_id": "FsNodeExistsError",
  "description": "Target object already exists.",
  "detail": "File named \"report.pdf\" already exists",
  "existing_node_id": "...",
  "existing_type": "file"
}
```

All errors should follow [Security](../system_core/security.md) practices (clear messages, no leaking sensitive info).

## Related docs
- [Models & data model](../system_core/models_data_model.md)
- [Storage backends](../system_core/storage_backends.md)
- [Security](../system_core/security.md)
- [Recursive deletion/background jobs](../system_core/recursive_deletion_background_jobs.md)
- [Sharing & signed tokens](../system_core/sharing_signed_tokens.md)
