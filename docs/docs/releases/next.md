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
- In-browser image preview and storage configuration forms in the admin.

## Added

- Public shares rooted at an `FsNode`, with optional expiration and manual revocation.
- Signed download tokens bound to the share, file and expiration time.
- `ShareDownload` records with IP address, user agent and timestamp for auditing.
- Recursive deletion via `FsNodeDeletionJob` and the `run_deletion_worker` management
  command, with batch processing, retries and stale-job recovery.
- Image preview in the SPA.
- Logout from the SPA.
- Storage settings forms in the Django admin.

## Changed

- `DELETE` requests for non-empty directories now return `202 Accepted` with a job id
  instead of deleting synchronously.
- The SPA handles node creation and rename ordering correctly.

## Security

- Signed token signatures are verified with constant-time comparison.
- Share access is validated against expiration, revocation and deleted nodes.

## Upgrade notes

- Apply migrations: `polyfile migrate`.
- Run the deletion worker as a separate process: `polyfile run_deletion_worker`.
  `runserver` does not start it, and recursive deletions stay pending without it.
- Public sharing depends on `SECRET_KEY`; keep it stable and secret, otherwise existing
  signed download links will stop validating.
