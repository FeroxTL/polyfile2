# Recursive deletion/background jobs

## Why asynchronous deletion?

Deleting large directory trees can involve removing thousands of files from storage and database records. Doing this synchronously in an HTTP request would be slow and unreliable. Polyfile instead marks nodes for deletion and processes them in the background.

## Deletion flow

1. **Request**: Client sends `DELETE` to the [API](../operations/api_reference.md#delete-node) for a path, with `?permanent=true` to bypass the Trash.

2. **Immediate response**: The API returns `202 Accepted` with `job_id` and status (deletion is accepted, not completed).

3. **Tombstoning**: `remove_fs_node()` creates a [FsNodeDeletionJob](models_data_model.md#fsnodedeletionjob), marks affected [FsNode](models_data_model.md#fsnode) objects as deleted (`deleted_at` set), and links them to the job. This is done in a transaction.

4. **Background processing**: The `run_deletion_worker` management command picks up the job and performs physical deletion.

5. **Cleanup**: Files are removed from the [storage backend](storage_backends.md) via `delete_many()`, nodes are removed from the database, and the job is marked complete/failed.

### One marking algorithm for permanent deletion and trash purging

`utils.mark_subtree_for_deletion(user, root, deletion_mode)` implements both cases. It partitions the subtree into:

- **protected** — nodes that must survive: trash entries belonging to a *foreign* batch (always protected in `permanent` mode), already retained scaffolding, and rows of another in-flight job;
- **retained ancestors** — ancestors of protected nodes; they get `trash_retained_at` and lose their trash flags, becoming invisible scaffolding that still holds the path;
- **doomed** — everything else, tombstoned with `deleted_at` + `deletion_job`.

This is why deleting a directory permanently leaves files that were previously moved to the Trash untouched: they stay visible in the trash, and only their ancestor directories become retained scaffolding.

## Trash

Nodes are not deleted immediately by default: `DELETE /api/v1/fs-node/<uuid>/` moves them to the Trash (see `apps/storage/trash_service.py` and the [API reference](../operations/api_reference.md#trash)).

- **States**: active / trashed (`trashed_at`, `trash_batch_id`, `trash_purge_after`) / retained scaffolding (`trash_retained_at`) / tombstone (`deleted_at`).
- **Entries**: the objects the user actually deleted. A multi-select delete sends one `DELETE` per node, so each node becomes its own entry and is restored independently. Deleting a directory that already contains trashed items produces two entries.
- **Restore**: the node never leaves the tree, so it returns to the exact path stored in the database. Retained ancestors are un-hidden; a same-name active directory is merged into, a same-name file forces a `name (N)` rename. Trashed ancestors are restored implicitly (chain restore).
- **Purge**: only the entry's own batch is removed. Nested trash entries survive and stay visible; their ancestors become retained scaffolding, and a later restore of such an entry turns the scaffolding back into plain active (empty) directories.
- **Reaper**: `reap_trash_scaffolding()` deletes retained directories that no longer have children, bottom-up.

## TTL sweep

Expired entries (`trash_purge_after <= now`) are purged automatically:

- inside `run_deletion_worker`, throttled by `--trash-sweep-interval` (seconds, default `300`, `0` disables);
- or via the `purge_expired_trash` management command for cron-based deployments (`--no-reap` skips the scaffolding cleanup).

Both only *create* the deletion jobs; the physical removal is still performed by the worker.

## FsNodeDeletionJob states

Jobs track progress and lifecycle:
- **pending** - Queued, waiting to be claimed
- **running** - Claimed by a worker and being processed
- **done** - All nodes processed successfully
- **failed** - Failed after max attempts or unexpected error
- **timeout** - Stale job that exceeded lock/attempt limits
- **cancelled** - Manually cancelled (if applicable)

For detailed fields and behavior, see [Models & data model](models_data_model.md#fsnodedeletionjob).

## run_deletion_worker

Management command: `python manage.py run_deletion_worker` (in `apps.storage.management.commands.run_deletion_worker`).

The worker is a separate process. The Django development server (`runserver`) and the application server do not
start it, so it must be run alongside them in every environment; otherwise deletion jobs remain pending.

### Key features
- **Leaf-first deletion**: Files are deleted before directories to ensure directories become empty before removal.
- **Batch processing**: Processes nodes in configurable batches for efficiency and memory control.
- **Concurrency safe**: Uses `select_for_update(skip_locked=True)` to claim jobs without blocking.
- **Stale job reanimation**: Recovers jobs stuck in running state (timeouts/crashes).
- **Retry logic**: Tracks attempts and marks failed after exceeding max attempts.
- **Graceful shutdown**: Handles SIGINT/SIGTERM.

### Options
```bash
python manage.py run_deletion_worker [--once] [--sleep SECONDS] [--batch-size N] [--lock-timeout SECONDS] [--max-attempts N] [--trash-sweep-interval SECONDS]
```

`--trash-sweep-interval` controls how often expired trash entries are enqueued for purging (default `300`; `0` disables the sweep).

## purge_expired_trash

Management command: `python manage.py purge_expired_trash [--no-reap]`

Enqueues purge jobs for trash entries past their TTL and removes childless retained scaffolding. Intended for cron-like setups that do not run the long-lived worker; it does not remove anything physically (the worker does).

## Backend integration

The deletion worker uses the backend for each node's storage via [StorageBackend.delete_many()](storage_backends.md#abstraction-layer). This allows efficient bulk deletion and proper error reporting per file.

## Monitoring

Job status can be checked via API: `GET /api/v1/fs-node/deletion-jobs/<uuid:job_id>/` ([API reference](../operations/api_reference.md#deletion-job-status)).

## Related docs
- [Models & data model](models_data_model.md)
- [Storage backends](storage_backends.md)
- [API reference](../operations/api_reference.md)
- [Security](security.md)
