# Recursive deletion/background jobs

## Why asynchronous deletion?

Deleting large directory trees can involve removing thousands of files from storage and database records. Doing this synchronously in an HTTP request would be slow and unreliable. Polyfile instead marks nodes for deletion and processes them in the background.

## Deletion flow

1. **Request**: Client sends `DELETE` to the [API](../operations/api_reference.md#delete-node) for a path.

2. **Immediate response**: The API returns `202 Accepted` with `job_id` and status (deletion is accepted, not completed).

3. **Tombstoning**: `remove_fs_node()` creates a [FsNodeDeletionJob](models_data_model.md#fsnodedeletionjob), marks affected [FsNode](models_data_model.md#fsnode) objects as deleted (`deleted_at` set), and links them to the job. This is done in a transaction.

4. **Background processing**: The `run_deletion_worker` management command picks up the job and performs physical deletion.

5. **Cleanup**: Files are removed from the [storage backend](storage_backends.md) via `delete_many()`, nodes are removed from the database, and the job is marked complete/failed.

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
python manage.py run_deletion_worker [--once] [--sleep SECONDS] [--batch-size N] [--lock-timeout SECONDS] [--max-attempts N]
```

## Backend integration

The deletion worker uses the backend for each node's storage via [FsBackendBase.delete_many()](storage_backends.md#abstraction-layer). This allows efficient bulk deletion and proper error reporting per file.

## Monitoring

Job status can be checked via API: `GET /api/v1/fs-node/deletion-jobs/<uuid:job_id>/` ([API reference](../operations/api_reference.md#deletion-job-status)).

## Related docs
- [Models & data model](models_data_model.md)
- [Storage backends](storage_backends.md)
- [API reference](../operations/api_reference.md)
- [Security](security.md)
