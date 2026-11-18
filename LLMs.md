# Project Context: Polyfile

## Overview
Polyfile is a system for managing and sharing files using a signed token mechanism. The project is currently transitioning from path-based URLs to opaque, signed tokens to improve security and database query efficiency.

## Tech Stack
- **Backend**: Django (Python)
- **Frontend**: Mithril.js

## Core Architecture
- **Storage Service**: Backend-agnostic file handling.
- **Share App**: High-level sharing logic, including HMAC signature generation and Base36 encoding.
- **Signed Tokens**: 
    - Uses HMAC-SHA256 for signatures.
    - Tokens are Base36 encoded.
    - Implementation details (truncation, etc.) are specific and should not be changed without explicit instruction.

## Key Directories & Files
- `apps/storage`: Storage service views and logic.
- `apps/share`: Sharing utils and token generation.
- `docs/implementation_plan_signed_tokens.md`: Primary source of truth for current goals.

## Current State & Goals
- **Signed Tokens**: Fully implemented for public share downloads. Uses HMAC-SHA256 and Base36 encoding.
- **Recursive Deletion**: Asynchronous background deletion system implemented using `FsNodeDeletionJob`.
- **Structure**: Distinction between `polyfile` and `polyfile2` is maintained for versioning/migration.

## Coding Standards & Constraints
- Maintain the separation between `storage` and `share` logic.
- Respect the cryptographic implementation of the signed tokens.
- Be aware of the `polyfile` vs `polyfile2` structure.

## Recursive Directory Deletion
The system supports asynchronous recursive directory deletion.
- **Mechanism**: Uses `FsNodeDeletionJob` to manage background deletion tasks. Jobs identify the subtree root by `root_node_uuid` + `root_node_name`. `FsNode` entities include `deleted_at` (timestamp) and `deletion_job` (foreign key) fields.
- **API Behavior**: `DELETE /api/v1/fs-node/<uuid:node_id>/?permanent=true` returns `202 Accepted` immediately (without the flag the node goes to the trash, see below). Nodes are marked as deleted in a transaction; physical removal happens in the background.
- **Background Worker**: A management command `run_deletion_worker` processes deletions in batches using a leaf-first strategy (files before directories).
- **Storage Backends**: `FsBackendBase` includes a `delete_many` method to support efficient bulk deletions.
- **Constraints**: Implements partial unique constraints on `FsNode` to allow "tombstones" (deleted nodes) while preserving uniqueness for active nodes.
- **Single marking algorithm**: `utils.mark_subtree_for_deletion(user, root, deletion_mode)` is shared by permanent deletion (`permanent`) and trash purging (`purge`). It partitions the subtree into *doomed* (tombstoned), *protected* (trash entries of foreign batches, retained scaffolding, mid-purge rows) and *retained ancestors* of protected nodes.

## Trash (recycle bin)
Trash state lives on `FsNode`: `trashed_at`, `trash_batch_id`, `trash_purge_after`, `trash_retained_at`. `FsNode` has three visible states plus a tombstone:
- **active** (all NULL) — visible in the file manager.
- **trashed** (`trashed_at`) — visible only in the trash; the subtree of one DELETE shares one `trash_batch_id`.
- **retained scaffolding** (`trash_retained_at`) — directories kept only as a path to trashed descendants; invisible everywhere.

**Managers:** `FsNode.active` (all three NULL), `FsNode.trash` (trashed and still restorable), `FsNode.objects` (everything). The partial unique constraints require all three timestamps to be NULL, so a trashed or retained node never blocks a same-name active sibling.

**Invariants:** an active node has only active ancestors; a trash entry root is a trashed node whose parent is not trashed by the same batch; a retained subtree contains only trashed/retained/tombstoned nodes.

**Lifecycle** (`apps/storage/trash_service.py`):
- `trash_fs_node`: marks the active subtree with a fresh batch (nested entries keep their own batch/TTL), revokes shares, cancels `TempUpload`s and releases archive manifests. Synchronous (`200`).
- `restore_fs_node(user, entry_id, on_conflict)`: the node never leaves the tree, so it returns to the exact path stored in the DB. Retained ancestors are un-hidden on the way; a same-name active directory is **merged** into (children re-parented, scaffolding row deleted), a same-name file forces a rename `name (N)`. Trashed ancestors are restored implicitly (chain restore) and reported in `restored_entries`; side effects are reported in `notices`.
- `purge_trash_entry` / `empty_trash`: purge the entry's own batch only. Nested trash entries survive and stay visible; their ancestors (including the entry root) become retained scaffolding. The same applies to the TTL sweep.
- `enqueue_expired_trash_purges`: creates deletion jobs for entries past `trash_purge_after`.
- `reap_trash_scaffolding`: deletes retained directories that no longer have children (bottom-up, repeated passes).

**API** (owner-scoped, 404 for foreign entries):
| Method | Path | Response |
|---|---|---|
| `DELETE` | `/api/v1/fs-node/<uuid>/` | `200` trash entry; `?permanent=true` → `202 {job_id}` |
| `GET` | `/api/v1/trash/` | `200 {"entries": [{id, name, type, trashed_at, trash_purge_after}]}`, newest first |
| `POST` | `/api/v1/trash/<uuid>/restore` | `200 {node, restored_entries, notices}`; `409 FsNodeExistsError` with `existing_node_id` |
| `DELETE` | `/api/v1/trash/<uuid>/` | `202 {job_id, status}` |
| `POST` | `/api/v1/trash/empty` | `202 {job_ids}` |

**TTL:** `POLYFILE_TRASH_TTL_DAYS` (env, default 30) is denormalized into `trash_purge_after` at trash time, so changing the setting does not affect existing entries. Sweeps run inside `run_deletion_worker` (`--trash-sweep-interval`, 0 disables) and via the `purge_expired_trash` command; both only *create* jobs — physical removal stays with the deletion worker.

**Frontend:** `/trash` route (`TrashDashboardView`) shows only the objects the user actually deleted (name, icon, date; nested content is not browsable); selection swaps the header for "Restore / Delete permanently", without selection it shows "Empty trash". `RestoreMonitorModal.js` mirrors the upload monitor: per-entry states, a "Keep both / Skip" question on `409`, and a summary of implicit restores and notices. The remove dialog has a "Delete permanently, bypassing the Trash" checkbox; cancelled uploads always delete permanently.

## FsNode identity (UUID migration, done)
- `FsNode.id` (UUID) is the canonical identifier for all mutations: create (`parent_id` + `name`), rename (`PATCH /api/v1/fs-node/<uuid:node_id>/` with `{name}`), move (same PATCH with `{parent_id}`; `null` = virtual root), delete (`DELETE .../<uuid>/`), share (`POST /api/shares/` with `node_id`).
- Rename changes only the leaf name: the UUID, parent, type, object key and public share links stay unchanged. Name validation is shared with create (`get_fs_node_name_validator`), active siblings must stay unique (`409 FsNodeExistsError` with `existing_node_id`/`existing_type`), and trashed/tombstoned names do not block the new name.
- Move changes only the parent: the UUID, leaf name, type, object key, public shares and the whole subtree stay unchanged, and `modified_at` is not touched (`save(update_fields=("parent",))`). A PATCH takes exactly one of `name`/`parent_id`; an empty body or both fields is a `400`. The destination must be an active owned directory on the same storage; self/subtree and cross-storage moves raise `400 FsNodeMoveError`, a file destination raises `409 NotADirectoryError`, and an active same-name sibling returns `409 FsNodeExistsError` (no auto-rename). Moving to the current parent is a no-op.
- Reads stay path-based for browser URLs (`/files/<path>`, `/s/<token>/<path>`) and also support `GET /api/v1/fs-node/<uuid:node_id>/`.
- The dashboard loads a directory by UUID whenever it already knows it: double-clicks and breadcrumb clicks preload the target by UUID before the path-based route change, and the server embeds the initial node UUID into the HTML (`initial-fs-node`). The `/files/<path>` URL never changes, and the path lookup remains the fallback (deep links, reloads without matching initial node data, external links).
- Responses include `id`, `parent_id` and `ancestors` (root → parent, clipped at the share root for public shares). There is no `path` field: the frontend derives the display path from `ancestors` + `current.name` (`FsNodeList.pathSegments` / `FsNodeList.path`), hiding the share root's name for public shares.
- `FsNode` no longer has a `path` property; paths are derived from the ancestor chain on the client (`FsNodeList.path`), and the share list page resolves the path lazily via `GET /api/v1/fs-node/<uuid:node_id>/` only when the user navigates. For shared directories that response is reused directly by the dashboard view (`markPathPending` + `consumePendingPath`), so it is not fetched a second time by path.

## Upload queue & replacement (done)
- The SPA upload queue is `frontend/apps/dashboard/services/UploadManager.js`: sequential uploads, per-file states (`queued`/`creating`/`uploading`/`conflict`/`error`/`done`/`canceled`), byte-weighted overall progress, `retry`, `replace`, `skip`, `cancelAll`, and a `beforeunload` guard while `hasPendingWork` is true.
- UI lives in `frontend/apps/dashboard/modals/UploadMonitor.js`: `UploadMonitorDocked` (fixed bottom-right panel, desktop) and `UploadMonitorModal` (mobile). The actions menu is custom (no Bootstrap JS) and uses fixed positioning so the panel or modal cannot clip it.
- `POST /api/v1/fs-node/touch` accepts `replace: true`. An existing file node is reused, preserving its UUID and share links; directories cannot be replaced.
- Conflict responses (`409 FsNodeExistsError`) include `existing_node_id` and `existing_type`. `HttpException.extra` fields are merged into API error JSON.
- `save_upload()` writes replacements to a fresh object key and queues the previous key in `PendingObjectDeletion` only after the new content is stored. `run_deletion_worker` drains that outbox.

## Agent Handoff Context
- Previous work established the architectural pillars (Storage Service, Signed Tokens).
- The UUID identity migration is complete; path-based mutations are removed.
- Verify directory structure before starting new tasks to ensure correct repository context.
