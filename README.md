# Polyfile - Custom Storage Solution

Polyfile is a Django-based project designed to provide flexible file storage solutions with support for user accounts.
It offers modular architecture for integrating various storage backends and managing files efficiently.

# Current status

Proof-of-works. Nothing works stable, use at your own risk.

## Overview

Polyfile combines Django's robust framework with customizable storage capabilities,
allowing users to manage their files through both web interfaces and RESTful APIs.
The application supports multiple storage backends (e.g., local file system and S3)
and integrates seamlessly with Django’s built-in authentication system.

## Features

- **User Authentication**: Built on top of Django's user model for secure account management.
- **Custom Storage Backends**: Supports various storage solutions, including local path-based storage.
- **File Management API**: RESTful endpoints for uploading, listing, and managing files.

## Roadmap
- 0.1.0 (done)
  - [x] Support of at least one `Storage` backend (file system)
  - SPA (web):
    - [x] List files and directories
    - [x] Create directories
    - [x] Upload files
    - Submenu:
      - [x] Download files
      - [x] Remove single files / empty directories
    - [x] Basic file type icons (file and directory)
  - Admin interface (django)
    - [x] Manage users
    - [x] Manage storages, files and directories
  - User authentication
    - [x] Public auth form (not admin)


- 0.2.0
  - SPA
    - [ ] Handle correct order when FsNode created / renamed
    - [ ] Cache some data in HTML for '/disk/...' requests
    - [ ] Simple file viewer (at least images)
    - [ ] Shared access / public download
    - [ ] Remove nested directories (async?)
    - [ ] Upload queue
  - User authentication
    - [ ] Ban by ip address for incorrect password
    - [ ] Password reset
    - [ ] Logout from SPA


- x.x (Just plans, not exact version)
  - Internalization 
  - SPA
    - JavaScript prettify and code style
    - Right click menu support
  - Initial setup on first run
    - Create and log in superuser
    - Create and setup first `Storage`
    - Create non-empty default profile
  - Authentication
    - Custom auth mechanism (like oauth2)
  - Api and backend
    - User settings
    - Space limitations
      - Space used in SPA
      - Limit space per user / per storage / per group
    - Toasts (i.e. "directory created", "settings saved")
    - Continuous session (renew with each request, needs caching?)
    - Access tokens (to use in other applications)
      - Token permissions (CRUD + restrict for file/directory)
    - Image previews
    - Download directories (zip files)
    - Add Photos and Albums
    - Shared access between users
    - Public uploads
    - Trash bin
  - Background tasks
    - Storage migration
    - Sending email
    - Clear trash bin with interval
  - Storages
    - Support more storages (like `s3`, see `django-storages`)
    - New type: Proxy storage (`fsnode` not created, all info about structure retrieves from storage itself)
    - Search for files or content
  - Admin
    - Storage settings with forms (can be added in api too)
  - Plugin system
  - Native application
    - Sync application for computers
    - Sync application for phones
