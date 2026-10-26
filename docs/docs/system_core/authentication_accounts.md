# Authentication & accounts

## User model

Polyfile uses a custom user model: `apps.accounts.models.User`, which extends Django's `AbstractUser`. It is configured via `AUTH_USER_MODEL = 'accounts.User'`.

Key aspects:

- **Storage assignment**: Each user can be linked to a [FsStorage](models_data_model.md#fsstorage) via the `storage` ForeignKey (`null`/`blank` allowed, `on_delete=SET_NULL`). This determines which storage backend/filesystem root the user's files live in.
- **Display name**: The `full_name` property returns a combined first/last name or falls back to username.
- **Ownership**: [FsNode](models_data_model.md#fsnode) objects are owned by users; all file operations must validate ownership ([Security](security.md)).

## Authentication flow

- **Login URL**: Configured as `reverse_lazy('accounts-login')` in settings.
- **Routes**: Account URLs are included from `apps.accounts.urls`. Public auth forms are used (not the Django admin login for end users).
- **Logout**: Available via API endpoint `/api/v1/user/logout/` ([API reference](../operations/api_reference.md)).
- **Session-based auth**: Standard Django authentication is used; APIs assert `request.user.is_authenticated`.

## Storage requirements for file operations

Many file operations require the user to have a configured storage:

- Creating directories ([mkdir](../operations/api_reference.md#create-directory)) and files ([touch/initiate upload](../operations/api_reference.md#initiate-file-upload)) check `user.storage_id` and raise `InvalidUserStorageError` if missing.
- This ensures files are created in a valid backend location rather than failing unpredictably.

## Administration

The Django admin (`/admin/`) allows administrators to manage users, assign storages, and manage [FsNode](models_data_model.md), [shares](sharing_signed_tokens.md), and related objects. Storage settings/forms are available in admin as noted in the [Roadmap](../contributors/roadmap.md).

## Related docs
- [Models & data model](models_data_model.md)
- [Storage backends](storage_backends.md)
- [API reference](../operations/api_reference.md)
- [Security](security.md)
