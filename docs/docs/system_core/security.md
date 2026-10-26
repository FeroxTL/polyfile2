# Security

## Goals

Polyfile must ensure users can only access and manipulate their own files, cannot escape storage boundaries, and that uploads/downloads/sharing are handled safely. Every new feature should be reviewed against these concerns.

## Core threats & mitigations

### Path traversal
- **Risk**: A malicious user could craft paths like `../../etc/passwd` to access files outside their allowed area.
- **Mitigations**: All path operations go through the storage/tree logic with user/ownership checks. Backends should treat paths as logical paths resolved within the configured storage root. [Storage backends](storage_backends.md) and [models](models_data_model.md) enforce tree boundaries. Use [PurePosixPath](storage_backends.md#path-handling) for normalization.

### Insecure Direct Object References (IDOR)
- **Risk**: Accessing/modifying other users' [FsNode](models_data_model.md#fsnode) objects by guessing IDs/paths.
- **Mitigations**: All [API](../operations/api_reference.md) operations require authentication and validate ownership/permissions before any backend action. `FsNode` is tied to `owner` and accessed through user-scoped logic. Never trust client-supplied IDs without authorization checks.

### Malicious filenames / input
- **Risk**: Reserved/control characters can break filesystems or be used for injection.
- **Mitigations**: Enforce filename restrictions (see [Constraints](#constraints)). Sanitize/validate filenames on upload/creation. Backends use Django's `validate_file_name` where appropriate.

### Upload/download abuse
- **Risk**: Large uploads, wrong content types, or direct access to storage paths.
- **Mitigations**: Uploads go through the controlled flow with [TempUpload](models_data_model.md#tempupload) tokens ([API reference](../operations/api_reference.md)). [FileSystemBackend](storage_backends.md#file-system-backend) uses `RawFileParser` to validate `Content-Type` (rejects multipart) and `Content-Length`. Downloads go through controlled views using backend `download_url()` rather than exposing raw paths.

### Sharing exposure
- **Risk**: Leaked share links or tampered tokens.
- **Mitigations**: [Signed tokens](sharing_signed_tokens.md) use HMAC-SHA256 with `settings.SECRET_KEY`, constant-time comparison (`hmac.compare_digest`), expiration, and support revocation. Truncated signatures for compact URLs but still verified properly.

## Constraints

These constraints are enforced to keep the system portable and safe:

- **Total path length < 260 characters** - Prevents issues on Windows/NTFS. Deep nesting may require restructuring; long URLs (~2000 bytes) should be monitored.
- **Filename length <= 255 characters** - Compatible with common filesystems (ext4, NTFS, etc.).
- **Forbidden characters**: `< > : " / \ | ? *` - These are reserved/illegal on many platforms (especially Windows). Block them via cross-platform validation.
- **Ownership validation required** - Every operation touching `FsNode` must confirm the user owns or is authorized for it.
- **Tree integrity** - Directories cannot contain files as parents in invalid ways; non-empty directories cannot be deleted directly (see [Recursive deletion](recursive_deletion_background_jobs.md)); files require file attachments.

## Security practices

- **Exception handling**: Never use bare `except Exception:`. Use specific exceptions like `PolyfileError`, `StorageBackendError`, or Django exceptions (`PermissionDenied`, `NotFoundError`) with clear, actionable messages.
- **Secrets**: Keep `SECRET_KEY` unique and secure in production. Never commit secrets.
- **Debug mode**: Set `DEBUG=False` in production, configure `ALLOWED_HOSTS` properly.
- **HTTPS**: Use HTTPS in production with secure cookies/HSTS where appropriate.
- **Validation everywhere**: Validate on API boundaries, in models (`clean()`), and before backend operations.
- **Least privilege**: Backends only access files they are responsible for; jobs run with appropriate permissions.

## Related docs
- [Storage backends](storage_backends.md)
- [Sharing & signed tokens](sharing_signed_tokens.md)
- [Recursive deletion/background jobs](recursive_deletion_background_jobs.md)
- [API reference](../operations/api_reference.md)
- [Authentication & accounts](authentication_accounts.md)
