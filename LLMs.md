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
- Transitioning to signed tokens for public share downloads.
- Distinguishing between the `polyfile` and `polyfile2` directories (migration/versioning in progress).

## Coding Standards & Constraints
- Maintain the separation between `storage` and `share` logic.
- Respect the cryptographic implementation of the signed tokens.
- Be aware of the `polyfile` vs `polyfile2` structure.

## Agent Handoff Context
- Previous work established the architectural pillars (Storage Service, Signed Tokens).
- Migration from path-based URLs is the primary objective.
- Verify directory structure before starting new tasks to ensure correct repository context.
