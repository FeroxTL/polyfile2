# Roadmap

From README.md:

## Current status
Proof-of-works. Nothing works stable, use at your own risk.

## 0.1.0 (done)
- [x] Support of at least one `FsStorage` backend (file system)
- SPA (web):
  - [x] List files and directories
  - [x] Create directories
  - [x] Upload files
  - Submenu:
    - [x] Download files
    - [x] Remove single files / empty directories
  - [x] Basic file type icons (file and directory)
- Admin interface (django):
  - [x] Manage users
  - [x] Manage storages, files and directories
- User authentication:
  - [x] Public auth form (not admin)

## 0.2.0
- SPA:
  - [x] Handle correct order when FsNode created / renamed
  - [x] Simple file viewer (at least images)
  - [ ] Shared access / public download
  - [ ] Remove nested directories (async?) - **Implemented** via background worker
  - [ ] Upload queue
- User authentication:
  - [ ] Ban by ip address for incorrect password
  - [ ] Password reset
  - [x] Logout from SPA
- Admin:
  - [x] Storage settings with forms

## Future plans (x.x)
- Internalization
- SPA:
  - JavaScript prettify and code style
  - Right click menu support
  - Image viewer - zoom to cursor
- Initial setup on first run:
  - Create and log in superuser
  - Create and setup first `FsStorage`
  - Create non-empty default profile
- Authentication:
  - Custom auth mechanism (like oauth2)
- API and backend:
  - User settings
  - Space limitations (per user/per storage/per group, show used space)
  - Toasts (notifications)
  - Continuous session (renew with each request)
  - Access tokens with permissions (CRUD + restrict for file/directory)
  - Image previews
  - Download directories (zip files)
  - Add Photos and Albums
  - Shared access between users
  - Public uploads
  - Trash bin
- Background tasks:
  - Storage migration
  - Sending email
  - Clear trash bin with interval
- Storages:
  - Support more storages (like S3, see django-storages)
  - New type: Proxy storage (FsNode not created, structure retrieved from storage)
  - Search for files or content
- Plugin system
- Native application:
  - Sync application for computers
  - Sync application for phones
