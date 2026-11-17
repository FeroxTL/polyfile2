# Next release

**Target:** `0.2.0`
**Status:** Unreleased

This is the working journal for the next version. Add every user-visible change here as it
merges. At release, rename this file to `<version>.md`, add the release date, finalize the
upgrade notes, and create a fresh `next.md` for the following version.

Remaining work for this release is tracked in the [Roadmap](../contributors/roadmap.md).

## Highlights

- Public sharing with time-limited, revocable links.
- HMAC-SHA256 signed download tokens that do not expose internal paths or node ids.
- Asynchronous recursive directory deletion handled by a background worker.
- Directory downloads as zip archives handled by an archive worker.
- In-browser upload queue with a live progress monitor and conflict-aware replacement.
- In-browser image preview and storage configuration forms in the admin.

## Added

- Public shares rooted at an `FsNode`, with optional expiration and manual revocation.
- Signed download tokens bound to the share, file and expiration time.
- `ShareDownload` records with IP address, user agent and timestamp for auditing.
- Recursive deletion via `FsNodeDeletionJob` and the `run_deletion_worker` management
  command, with batch processing, retries and stale-job recovery.
- Download directories as zip archives via async archive jobs (`FsNodeArchiveJob`) and the
  `run_archive_worker` background worker, with ZIP delivery through the archive backend and
  status polling endpoints.
- An upload queue in the SPA that uploads files sequentially and shows per-file state,
  overall byte progress and a completed/total file count.
- A docked upload monitor in the bottom-right corner on desktop and a standard modal on
  mobile, reachable from the navbar with a badge for active uploads.
- Inline conflict handling: replace the existing file, skip it, or retry network and server
  failures. Canceling aborts in-flight requests and removes placeholder nodes created by the
  queue.
- A `beforeunload` confirmation while uploads are still pending.
- File replacement through `replace: true` on `POST /api/v1/fs-node/touch`. The existing
  `FsNode` is reused, so its UUID and share links keep working.
- Conflict responses include `existing_node_id` and `existing_type`, so clients can tell
  whether the name belongs to a file that can be replaced.
- Image preview in the SPA.
- Logout from the SPA.
- Storage settings forms in the Django admin.
- Hashed API keys for non-session API clients, managed with the
  `create_api_key` management command and the Django admin.
- Temporary IP-based lockout after repeated failed login attempts or invalid API keys,
  powered by django-axes. Login lockouts render a styled page; API-key lockouts return
  HTTP 429.
- A standalone load-testing harness (locust + httpx) with an API smoke flow, a disk-usage guard and static HTML reports, living in the separate `polyfile-e2e` project under its `perf_tests/` directory.
- Trash (recycle bin): deleted nodes are kept restorable for 30 days (configurable with
  `POLYFILE_TRASH_TTL_DAYS`), listed under `/trash`, restorable to their original path and
  purgeable individually or all at once. Public links are revoked when a node is trashed.

## Changed

- `DELETE /api/v1/fs-node/<uuid>/` now moves the node to the Trash and returns `200` with
  the trashed entry. Use `?permanent=true` for the previous asynchronous deletion
  (`202 Accepted` with a job id).
- Permanently deleting a directory leaves files that were previously trashed untouched:
  they stay in the Trash, and only the ancestor directories become invisible scaffolding.
- `DELETE` requests for non-empty directories now return `202 Accepted` with a job id
  instead of deleting synchronously.
- `POST /api/v1/fs-node/touch` accepts an optional `replace` flag (default `false`) and
  issues a fresh `TempUpload` token on every call, including replacements.
- Replacing a file uploads to a fresh object key and switches the node only after the new
  content is stored. The previous object is queued for deletion, so a failed upload leaves
  the current file untouched.
- API error responses now forward any extra fields attached to the exception (for example,
  conflict details), in addition to `error_id`, `description` and `detail`.
- The SPA handles node creation and rename ordering correctly.

## Security

- Signed token signatures are verified with constant-time comparison.
- Share access is validated against expiration, revocation and deleted nodes.
- API keys are stored as HMAC-SHA256 digests; plaintext tokens are shown only once.
- Brute-force protection via django-axes: lockouts are based on IP + username for
  logins and IP for API keys.

## Upgrade notes

- Apply migrations: `polyfile migrate`. This includes django-axes migrations that add
  `AccessAttempt`, `AccessLog` and related tables, and the trash fields on `FsNode`.
- Trash entries are purged by `run_deletion_worker` (sweep every 300 seconds by default,
  `--trash-sweep-interval 0` disables it) or by the `purge_expired_trash` command when the
  worker is not run as a daemon.
- Configure `AXES_BEHIND_PROXY`, `AXES_IPWARE_PROXY_COUNT` and
  `AXES_IPWARE_META_PRECEDENCE_ORDER` when running behind a reverse proxy.
- API keys require the new `accounts.0003_apikey` migration. Set
  `API_KEY_HASH_KEY` in production if key hashes should be rotated separately
  from `SECRET_KEY`.
- Run the deletion worker as a separate process: `polyfile run_deletion_worker`.
  `runserver` does not start it, and recursive deletions stay pending without it.
- The deletion worker also drains `PendingObjectDeletion`, which now receives the previous
  object of every replaced file. Without the worker, replaced content stays on disk even
  though the database already points to the new object.
- Public sharing depends on `SECRET_KEY`; keep it stable and secret, otherwise existing
  signed download links will stop validating.
