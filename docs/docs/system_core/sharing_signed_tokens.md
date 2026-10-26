# Sharing & signed tokens

## Purpose

Polyfile allows sharing files/directories publicly via `SharedNode`. The sharing system is moving away from exposing raw paths/IDs toward opaque, signed tokens for better security and query efficiency.

## How sharing works

### SharedNode
A `SharedNode` represents a public share rooted at a [FsNode](models_data_model.md#fsnode). When created, it points to the root node of the shared subtree and defines its lifecycle - shares can be time-limited with `expires_at` and can be manually revoked with `revoked_at`. A share is only valid if it hasn't been revoked, hasn't expired, and its root node hasn't been deleted. The `active` manager enforces these rules automatically.

### ShareDownload
Every download through a share creates a `ShareDownload` record logging access details (IP address, user agent, timestamp). This provides an audit trail and forms the basis for future download limits and statistics.

### Signed tokens for secure downloads
Downloads within shares don't use the share token alone - they use cryptographically signed download tokens. This prevents tampering and ensures links expire. The mechanism binds the share, specific file, and expiration time together with an HMAC signature.

## Signed token mechanism

Implemented in `apps.share.utils`, the system uses HMAC-SHA256 with Base36-encoded timestamps for compact, secure URLs.

### How it works

1. **Time encoding**: Expiration time is converted to minute offset from `BASE_DATE` (2020-01-01 00:00:00 UTC) and encoded as Base36. This keeps URLs compact.

2. **Payload construction**: A payload is built as `f"{share_token}|{fs_node_pk}|{time_offset}"` to uniquely bind the share, specific file, and expiration.

3. **Signature generation**: HMAC-SHA256 is computed using `settings.SECRET_KEY`. For URL compactness, only the first 16 hex characters of the signature are used.

4. **Validation**: When validating, the signature is recomputed and compared using `hmac.compare_digest` (constant-time comparison to prevent timing attacks). The expiration time is decoded and checked against current time. Invalid signatures or expired links are rejected.

### URL helpers

- `get_public_share_url(request, share_token)` - Builds absolute URL to the share root
- `share_download_url(share_token, fs_node_id)` - Builds a signed download URL for a specific file within the share

## Security notes

- Implementation details (truncation to 16 chars, payload format) should not be changed without explicit instruction.
- Always use constant-time comparison for signatures.
- Expiration and revocation are strictly enforced.
- Keep `SECRET_KEY` secure - it's critical for signature verification ([Security](security.md)).

## Related docs

- [API reference](../operations/api_reference.md)
- [Security](security.md)
- [Models & data model](models_data_model.md)
- [Authentication & accounts](authentication_accounts.md)
