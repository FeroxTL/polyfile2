# Architecture overview

## Project structure

Polyfile is a Django-based file manager with a Mithril.js SPA frontend. The project is organized as follows:

```
polyfile/
├── apps/
│   ├── accounts/     # User authentication and account management
│   ├── share/        # Public sharing and signed token functionality
│   └── storage/      # Core file storage, FsNode model, APIs
├── contrib/
│   └── backends/     # Storage backend implementations
├── core/             # Django project settings, URLs, base API
└── web_assets/       # Built frontend assets (production)
```

## Key components

### Backend (Django)
- **Django 5.2.18** - Web framework
- **Custom User model** (`apps.accounts.models.User`) - Extends `AbstractUser`, linked to `FsStorage`
- **Storage service** (`apps.storage`) - Core file management logic, FsNode abstraction
- **Share service** (`apps.share`) - Public sharing with signed tokens (HMAC-SHA256, Base36)
- **REST API** - Path-based API in `apps.storage.api`, generic components in `polyfile.core.rest`/`core.api`

### Frontend (Mithril.js)
- **Mithril.js 2.3.8** - SPA framework
- **Bootstrap 5.3.8** - UI components
- **Webpack 5** - Bundling, outputs to `web_dev_assets/` (dev) or `polyfile/web_assets/` (prod)
- **FontAwesome** - Icons

### Storage abstraction
- **FsNode** - Core entity representing files and directories in a tree structure
- **FsStorage** - Configuration for storage backends
- **FsBackendBase** - Abstract base for all storage backends (extends Django's `Storage`)
- **FileSystemBackend** - Local filesystem implementation

## Design principles

- **Path-based API** - Logical paths like `/api/files/folder/file.txt` 
- **Recursive tree format** - API returns nested structure with `current` node and `children`
- **Tombstone pattern** - Soft deletes via `deleted_at` for background cleanup
- **Signed tokens** - Secure public sharing without exposing internal paths/IDs directly
- **Backend-agnostic** - Storage layer abstracts physical storage implementation
- **CTE-based queries** - Uses `django-cte` for efficient tree traversal with path computation
