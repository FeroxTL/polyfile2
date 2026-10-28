# Polyfile

**A self-hosted file workspace where the file tree lives in the database and the bytes live in a pluggable storage backend.**

Polyfile is not a filesystem browser bolted onto Django admin. It is a storage application built around one
deliberate separation: the logical structure of your files and the physical place where their content is stored
are two different things. Every file and directory is an [`FsNode`](system_core/models_data_model.md#fsnode)
record in a database-backed tree, while the actual bytes are written through a storage backend
(`FileSystemBackend` today, other providers on the roadmap). The web client and the REST API only ever deal with
logical paths, never with raw disk locations.

That split is the core of the project. It makes it possible to give different users different storage roots,
swap a backend without rewriting the UI, share a subtree without exposing internal paths, and delete a deep
directory tree without holding an HTTP request open for minutes.

## What that means in practice

- **Directories are virtual.** Creating a directory adds a node to the tree; it does not have to create a real
  folder on disk. The hierarchy is stored as parent-child relationships and resolved with recursive CTEs
  (`django-cte`), so full paths are computed in SQL instead of by walking the filesystem.
- **Paths are logical, not physical.** A path like `/projects/2026/report.pdf` identifies a node in Polyfile's
  tree. Where that file actually lives is decided by the node's `FsStorage` and its backend.
- **Storage is a configuration detail.** Each user can be assigned an `FsStorage` with its own backend and options.
  A single installation can therefore serve several independent storage roots, and moving to a new backend is an
  implementation task rather than an API change.
- **Uploads are explicit two-step transfers.** Creating a file returns a `TempUpload` token and an upload URL; the
  raw bytes are sent separately. That keeps metadata creation, validation, MD5 calculation, MIME detection and the
  actual transfer under the application's control.
- **Deletion is asynchronous by design.** Removing a directory returns `202 Accepted` with a job id. A background
  worker walks the subtree leaf-first, removes physical files in batches and cleans up the database records.
- **Public sharing uses signed, expiring tokens.** Share links do not expose node ids or internal paths. Download
  links are bound to the share, the specific file and an expiration time with an HMAC-SHA256 signature.

## Features

- **Web file manager (SPA)** — browse the tree, create directories, upload files, download, preview images, and
  delete files or empty directories. Built with Mithril.js and Bootstrap 5.
- **Path-based REST API** — list nodes and their children, create directories, initiate uploads, delete subtrees,
  and poll deletion jobs. See the [API reference](operations/api_reference.md).
- **Backend-agnostic storage** — a common `FsBackendBase` contract with a reference local filesystem backend.
  Adding S3, FTP or another provider means implementing the backend, not changing the tree logic.
- **Public shares** — time-limited and revocable shares, signed download URLs, and a `ShareDownload` audit log of
  IP address, user agent and timestamp.
- **Recursive deletion worker** — batch processing, `select_for_update(skip_locked=True)`, stale-job recovery,
  retries and graceful shutdown.
- **Django admin integration** — manage users, assign storages, and inspect files, directories and shares.
- **Cross-platform guardrails** — path length under 260 characters, filenames up to 255 characters, and a
  forbidden-character set that keeps names valid on Windows, macOS, Linux and object storage.

## How the pieces fit

| Layer | Responsibility | Where to read more |
| --- | --- | --- |
| Data model | `FsNode` tree, `FsStorage` configuration, upload and deletion state | [Models & data model](system_core/models_data_model.md) |
| Storage | Reading, writing and deleting bytes through `FsBackendBase` | [Storage backends](system_core/storage_backends.md) |
| API | Authenticated path-based endpoints for the SPA and integrations | [API reference](operations/api_reference.md) |
| Sharing | Public share lifecycle and HMAC-signed download tokens | [Sharing & signed tokens](system_core/sharing_signed_tokens.md) |
| Background jobs | Asynchronous recursive deletion and job status | [Recursive deletion](system_core/recursive_deletion_background_jobs.md) |
| Frontend | Mithril.js SPA and its Django/Webpack integration | [Frontend architecture](system_core/frontend_architecture.md) |
| Security | Path traversal, IDOR, upload validation and input constraints | [Security](system_core/security.md) |

## Quick start

```bash
git clone <REPOSITORY_URL>
cd polyfile2

uv sync
cd frontend && npm install && npm run build_dev && cd ..

# create .env with SECRET_KEY, DEBUG and ALLOWED_HOSTS
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver

# in a second terminal — required for recursive deletion
uv run python manage.py run_deletion_worker
```

`runserver` does **not** start the deletion worker. Without it, `DELETE` requests still return `202 Accepted`
and create a deletion job, but the physical files are never removed and the jobs stay pending.

Open `http://127.0.0.1:8000`, sign in, and assign an `FsStorage` to your user in the Django admin before creating
files. The full sequence, including the wheel-based installation, is in
[Installation & configuration](operations/installation.md).

## Popular sections

### Start here
- [Installation & configuration](operations/installation.md) — run Polyfile from source or from a wheel.
- [Architecture overview](system_core/architecture_overview.md) — project layout and the main design decisions.
- [API reference](operations/api_reference.md) — endpoints, request parameters and response shapes.
- [Security](system_core/security.md) — the threats Polyfile is designed to resist and the rules every feature follows.

### Core concepts
- [Models & data model](system_core/models_data_model.md) — `FsNode`, `FsStorage`, `TempUpload` and CTE-based paths.
- [Storage backends](system_core/storage_backends.md) — how bytes are stored, uploaded, downloaded and deleted.
- [Sharing & signed tokens](system_core/sharing_signed_tokens.md) — how public links stay compact and tamper-resistant.
- [Recursive deletion & background jobs](system_core/recursive_deletion_background_jobs.md) — why deletes are jobs and how the worker runs them.
- [Frontend architecture](system_core/frontend_architecture.md) — the Mithril.js SPA, build outputs and coding standards.

### Running it
- [Configuration for deployment](operations/configuration_for_deployment.md) — production checklist.
- [Environment variables](operations/environment_variables.md) — every supported setting.
- [Building a distribution](operations/packaging.md) — wheel, frontend assets and bundled documentation.

### Contributing
- [Development workflow](contributors/development_workflow.md) — commands, linting and project conventions.
- [Testing](contributors/testing.md) — backend and frontend test suites.
- [Roadmap](contributors/roadmap.md) — what is done, what is next, and what is only planned.

## Project status

Polyfile is at an early stage. Version `0.1.0` established the core file tree and web UI; `0.2.0` added public
sharing, signed download tokens and asynchronous recursive deletion. Expect rough edges and changing APIs — see
the [Roadmap](contributors/roadmap.md) for the current state. Planned work includes additional storage providers,
space limits, a trash bin, access tokens with per-node permissions, and a plugin system.
