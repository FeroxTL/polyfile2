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
- Image preview in the SPA.
- Logout from the SPA.
- Storage settings forms in the Django admin.
- Hashed API keys for non-session API clients, managed with the
  `create_api_key` management command and the Django admin.
- A standalone load-testing harness (locust + httpx) with an API smoke flow, a disk-usage guard and static HTML reports, living in the separate `polyfile-e2e` project under its `perf_tests/` directory.

## Changed

- `DELETE` requests for non-empty directories now return `202 Accepted` with a job id
  instead of deleting synchronously.
- The SPA handles node creation and rename ordering correctly.

## Security

- Signed token signatures are verified with constant-time comparison.
- Share access is validated against expiration, revocation and deleted nodes.
- API keys are stored as HMAC-SHA256 digests; plaintext tokens are shown only once.

## Upgrade notes

- Apply migrations: `polyfile migrate`.
- API keys require the new `accounts.0003_apikey` migration. Set
  `API_KEY_HASH_KEY` in production if key hashes should be rotated separately
  from `SECRET_KEY`.
- Run the deletion worker as a separate process: `polyfile run_deletion_worker`.
  `runserver` does not start it, and recursive deletions stay pending without it.
- Public sharing depends on `SECRET_KEY`; keep it stable and secret, otherwise existing
  signed download links will stop validating.
