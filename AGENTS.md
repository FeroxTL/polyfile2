# AGENTS.md - Polyfile2 Project Guidelines

## 1. Naming & Core Entities
To ensure consistency across the codebase, use the following naming conventions:

- **FsNode**: The primary entity representing both files and directories.
- **PurePosixPath**: Use `pathlib.PurePosixPath` for path manipulation logic to ensure consistent `/` separators regardless of the host OS.
- **FsBackend**: The base suffix for all storage provider implementations (e.g., `S3FsBackend`, `FTPFsBackend`).
- **FileSystemBackend**: The specific name for the backend that interacts with the local/native file system.

## 2. Agent Roles
- **Backend/Storage Expert**: Responsible for the `FileSystemBackend` logic, storage provider integrations, path manipulation, and database operations related to file metadata.
- **Frontend/UI Expert**: Responsible for the SPA (Mithril.js), state management, and ensuring the UI correctly reflects the `FsNode` structure using Bootstrap 5 components.
- **Security Auditor**: A specialized "review mode" for agents. Every new feature must be checked for:
    - Path Traversal vulnerabilities (ensuring users cannot escape their designated storage roots).
    - IDOR (ensuring users can only access/modify nodes they own or have permissions for).
    - Input sanitization of file names.

## 3. Project Constraints & Security
To ensure cross-platform compatibility (Windows, macOS, Linux, and Cloud Storage), all operations must respect these limits:

- **Path Length**: Maximum total path length should be kept under **260 characters** (compatibility with Windows/NTFS).
- **Filename Length**: Maximum length for a single filename is **255 characters**.
- **Character Restrictions**: Filenames must not contain reserved characters: `< > : " / \ | ? *`. We will use a cross-platform safe regex to enforce this.
- **URL Limits**: Since we use a Path-based API, we must monitor total URL length (limit ~2000 bytes). For very deep nesting, we may need to implement logic to alert the user or suggest restructuring.
- **Security**: All `FsNode` access must be validated against the owner/permissions before any backend operation.

## 4. Tech Stack
- **Backend**: Django (Standard Views), Marshmallow (Serialization/Deserialization).
- **Frontend**: Mithril.js, Bootstrap 5 (Package Manager: `npm`).
- **Frontend Testing**: Vitest.
- **Build Tool**: Webpack.
- **Database**: SQLite (development), PostgreSQL (production).
- **API Location**: Main file management APIs are in `polyfile/apps/storage/api.py`; generic API components are in `polyfile/core/rest`.

## 5. Development Standards
- **Testing**:
    - **Backend**: Use `django.test` and `unittest`.
    - **Frontend**: Use `vitest` for unit and integration tests.
    - **Browser E2E**: Use `pytest-playwright` with `pytest-django`'s `live_server`. Tests live in `test_suites/browser_tests/` and rely on the dedicated `polyfile.core.settings_e2e` settings module.
    - Use `factory-boy` for dynamic fixture creation.
    - Use file-based fixtures for large, static datasets where appropriate.
    - **Mandatory**: Every new feature must include tests. Existing tests must be updated/fixed when code changes.
- **Packaging**:
    - The build backend is `hatchling` (PEP 517); `python -m build` and `uv build` are equivalent frontends.
    - Run the production frontend build (`npm run build` in `frontend/`) and the docs build (`mkdocs build --strict`) before `python -m build`; a build hook rejects artifacts without `polyfile/web_assets/`, `polyfile/webpack-stats.json`, or `polyfile/docs/index.html`.
    - Built docs are distributed inside `polyfile/docs/`; the Markdown sources in `docs/` are not packaged.
    - `make assets`, `make dist`, and `make dist-check` are the canonical commands.
    - Runtime data (database, collected static, media) must go to `POLYFILE_DATA_DIR`, never into the installed package.
- **Coverage**:
    - **Backend**: Run `coverage run manage.py test` to ensure high test coverage.
    - **Frontend**: Run `npm run test:coverage` to ensure high test coverage.
- **Exception Handling**:
    - **Never** use a bare `except Exception:`.
    - Use specific exceptions: `PolyfileError`, `StorageBackendError`, or standard Django exceptions (e.g., `PermissionDenied`, `NotFoundError`).
    - Exceptions must provide clear, actionable messages.
- **Code Style**: Follow standard PEP 8. Use type hints where possible, especially in `FsBackend` method signatures.
- **Quotes**: Use double quotes (`"`) for strings as the project standard; we are gradually transitioning away from single quotes.
- **Development Standards**:
    - Use double quotes (`"`) for strings as the project standard; we are gradually transitioning away from single quotes.

## 6. API & Integration
- **UUID identity**: mutations address nodes by `FsNode.id` (UUID). Create via `parent_id + name`, delete via `DELETE /api/v1/fs-node/<uuid:node_id>/`, share via `POST /api/shares/` with `node_id`.
- **Path-based reading**: browser URLs and read endpoints stay path-based: `/api/v1/fs-node/?path=...`, `/files/<path>`, `/s/<token>/<path>`. UUID lookup is also available: `GET /api/v1/fs-node/<uuid:node_id>/`. The dashboard SPA loads by UUID when it already knows the node (double-click preload, breadcrumb preload, server-embedded `initial-fs-node`) and falls back to the path lookup.
- **Recursive Tree Format**: The API for listing nodes returns the node, its ancestors (root → parent, clipped at the share root for public shares) and its children:
  ```json
  {
    "current": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "parent_id": "6a2e8400-e29b-41d4-a716-446655440001",
      "name": "string",
      "type": "directory|file",
      "created_at": "timestamp",
      "modified_at": "timestamp",
      "size": 0,
      "mime_type": "string",
      "md5": "string",
      "file": "object_key",
      "download_url": "string"
    },
    "ancestors": [
      {"id": "b1c2...", "name": "parent-dir"}
    ],
    "children": [
      { "id": "...", "parent_id": "...", "name": "...", "type": "..." }
    ]
  }
  ```
  The virtual root has `"id": null` and empty `ancestors`. There is no `path` field: the frontend derives the display path from `ancestors` + `current.name` (hiding the share root's name for public shares).

## 7. Frontend Component Standards
- **Named Exports**: Always use named exports for components instead of default exports.
  - *Correct:* `export const FsNodeEmptyDirectoryView = () => { ... };`
  - *Incorrect:* `export default FsNodeEmptyDirectoryView;`
- This ensures consistent naming across the application and improves IDE auto-import support and refactoring.
- **Linting**: For all frontend changes, ensure code complies with ESLint rules. Run `npx eslint .` within the `frontend/` directory to check for errors before finalizing work.

## Architecture & Context
The `LLMs.md` file serves as the primary reference for project architecture, core specifications, and key implementation details. Agents should consult `LLMs.md` before starting new tasks to ensure alignment with the project's design and to respect established constraints.
