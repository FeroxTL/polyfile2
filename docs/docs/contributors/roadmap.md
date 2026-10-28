# Roadmap

This page is the single source of truth for planned work. It only looks forward: shipped
changes are recorded in [Release notes](../releases/index.md).

## Current status

Early-stage proof of work. APIs, storage layout and configuration may change without
notice. Do not use Polyfile as the only copy of important data.

## Next release — 0.2.0

This is the committed scope for the next release. Items move to the
[next release journal](../releases/next.md) as they are completed.

| Area | Feature | Status |
| --- | --- | --- |
| SPA | Upload queue | Planned |
| Authentication | Password reset | Planned |
| Authentication | Temporary IP ban after repeated failed logins | Planned |

## Later

Accepted work that is not scheduled for a specific release yet.

### Storage
- S3 backend and other providers via `django-storages`
- Proxy storage (structure read from the backend instead of `FsNode` records)
- Search across file names and content
- Storage migration between backends

### File management
- Trash bin with scheduled cleanup
- Download directories as zip archives
- Space limits per user, storage and group, with usage display
- Access tokens with CRUD and per-node permissions
- Sharing between users
- Public uploads
- User settings
- Toasts for completed actions
- Continuous session renewal
- Enhanced image previews and zoom
- Initial setup wizard for the first superuser and `FsStorage`

### Authentication
- Custom authentication mechanism, such as OAuth2

### SPA
- Right-click context menu
- JavaScript cleanup and style pass
- Internationalization

### Background tasks
- Sending email

## Ideas / under consideration

Not committed and not scheduled. These may change or never be implemented.

- Plugin system
- Photos and albums
- Native desktop and mobile sync applications
