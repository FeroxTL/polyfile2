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
- **API Location**: Main API views are located in `polyfile/core/rest`.

## 5. Development Standards
- **Testing**:
    - **Backend**: Use `django.test` and `unittest`.
    - **Frontend**: Use `vitest` for unit and integration tests.
    - Use `factory-boy` for dynamic fixture creation.
    - Use file-based fixtures for large, static datasets where appropriate.
    - **Mandatory**: Every new feature must include tests. Existing tests must be updated/fixed when code changes.
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
- **Path-based Routing**: The API should be accessible via logical paths (e.g., `/api/files/folder/file.txt`).
- **Recursive Tree Format**: The API for listing nodes should return a recursive structure:
  ```json
  {
    "current": {
      "name": "string",
      "type": "directory|file",
      "created_at": "timestamp",
      "modified_at": "timestamp",
      "size": 0,
      "mime_type": "string",
      "md5": "string",
      "file": "path_to_file",
      "download_url": "string",
      "path": "/..."
    },
    "children": [
      { "name": "...", "type": "...", ... }
    ]
  }
  ```

## 7. Frontend Component Standards
- **Named Exports**: Always use named exports for components instead of default exports.
  - *Correct:* `export const FsNodeEmptyDirectoryView = () => { ... };`
  - *Incorrect:* `export default FsNodeEmptyDirectoryView;`
- This ensures consistent naming across the application and improves IDE auto-import support and refactoring.
- **Linting**: For all frontend changes, ensure code complies with ESLint rules. Run `npx eslint .` within the `frontend/` directory to check for errors before finalizing work.
