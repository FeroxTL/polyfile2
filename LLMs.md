# Project Context: Polyfile

## Overview
Polyfile is a system for managing and sharing files using a signed token mechanism. The project is currently transitioning from path-based URLs to opaque, signed tokens to improve security and database query efficiency.

## Tech Stack
- **Backend**: Django (Python)
- **Frontend**: Mithril.js

## Core Architecture
- **Storage Service**: Backend-agnostic file handling.
- **Share App**: High-level sharing logic, including HMAC signature generation and Base36 encoding.
- **Signed Tokens**: 
    - Uses HMAC-SHA256 for signatures.
    - Tokens are Base36 encoded.
    - Implementation details (truncation, etc.) are specific and should not be changed without explicit instruction.

## Key Directories & Files
- `apps/storage`: Storage service views and logic.
- `apps/share`: Sharing utils and token generation.
- `docs/implementation_plan_signed_tokens.md`: Primary source of truth for current goals.

## Current State & Goals
- **Signed Tokens**: Fully implemented for public share downloads. Uses HMAC-SHA256 and Base36 encoding.
- **Recursive Deletion**: Asynchronous background deletion system implemented using `FsNodeDeletionJob`.
- **Structure**: Distinction between `polyfile` and `polyfile2` is maintained for versioning/migration.

## Coding Standards & Constraints
- Maintain the separation between `storage` and `share` logic.
- Respect the cryptographic implementation of the signed tokens.
- Be aware of the `polyfile` vs `polyfile2` structure.

## Recursive Directory Deletion
The system supports asynchronous recursive directory deletion.
- **Mechanism**: Uses `FsNodeDeletionJob` to manage background deletion tasks. Jobs identify the subtree root by `root_node_uuid` + `root_node_name`. `FsNode` entities include `deleted_at` (timestamp) and `deletion_job` (foreign key) fields.
- **API Behavior**: `DELETE /api/v1/fs-node/<uuid:node_id>/` returns `202 Accepted` immediately. Nodes are marked as deleted in a transaction; physical removal happens in the background.
- **Background Worker**: A management command `run_deletion_worker` processes deletions in batches using a leaf-first strategy (files before directories).
- **Storage Backends**: `FsBackendBase` includes a `delete_many` method to support efficient bulk deletions.
- **Constraints**: Implements partial unique constraints on `FsNode` to allow "tombstones" (deleted nodes) while preserving uniqueness for active nodes.

## FsNode identity (UUID migration, done)
- `FsNode.id` (UUID) is the canonical identifier for all mutations: create (`parent_id` + `name`), delete (`DELETE .../<uuid>/`), share (`POST /api/shares/` with `node_id`).
- Reads stay path-based for browser URLs (`/files/<path>`, `/s/<token>/<path>`) and also support `GET /api/v1/fs-node/<uuid:node_id>/`.
- The dashboard loads a directory by UUID whenever it already knows it: double-clicks and breadcrumb clicks preload the target by UUID before the path-based route change, and the server embeds the initial node UUID into the HTML (`initial-fs-node`). The `/files/<path>` URL never changes, and the path lookup remains the fallback (deep links, reloads without matching initial node data, external links).
- Responses include `id`, `parent_id` and `ancestors` (root → parent, clipped at the share root for public shares). There is no `path` field: the frontend derives the display path from `ancestors` + `current.name` (`FsNodeList.pathSegments` / `FsNodeList.path`), hiding the share root's name for public shares.
- `FsNode` no longer has a `path` property; paths are derived from the ancestor chain on the client (`FsNodeList.path`), and the share list page resolves the path lazily via `GET /api/v1/fs-node/<uuid:node_id>/` only when the user navigates. For shared directories that response is reused directly by the dashboard view (`markPathPending` + `consumePendingPath`), so it is not fetched a second time by path.

## Agent Handoff Context
- Previous work established the architectural pillars (Storage Service, Signed Tokens).
- The UUID identity migration is complete; path-based mutations are removed.
- Verify directory structure before starting new tasks to ensure correct repository context.
