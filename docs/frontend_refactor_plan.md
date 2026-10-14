# Frontend Refactor Plan: Shared File System Components

## Overview
The goal of this refactor is to consolidate common UI logic and functionality between the Dashboard and Share Detail pages into a shared core directory. This follows the DRY (Don't Repeat Yourself) principle to improve maintainability and ensure UI consistency.

## Target Directory
`C:\Users\ferox\PycharmProjects\polyfile2\frontend\core\components`

## Architectural Approach: Prop-based Configuration
To avoid creating a "God Object" (a component that tries to do everything for every page), the shared `FsNodeListView` will be designed as a "smart container" that accepts optional configuration props. This allows it to handle the common logic (loading, errors, selection) while allowing each page to "plug in" its unique features (breadcrumbs, action bars, etc.).

---

## Phase 1: Atomic UI Components
**Goal:** Extract the smallest, most independent pieces of UI.

1. **`FsNodeItemView.js`**: 
    *   A "dumb" UI component.
    *   Responsibility: Rendering a single list row.
    *   Inputs: `fsNode` object.
2.  **Status Components**:
    *   Extract "Loading" spinner UI.
    *   Extract "Error Card" UI.
    *   Ensure consistent styling and messaging across both apps.

## Phase 2: The Core List Component (`FsNodeListView.js`)
**Goal:** Consolidate high-level logic and lifecycle management.

Create a shared `FsNodeListView` that handles:
*   **Event Management**: `onDocumentClick`, `oncreate`, and `onremove` listeners.
*   **State Management**: Checking `FsNodeList.xhr` and `FsNodeList.error`.
* **Mapping**: Iterating over `FsNodeList.elements` to render `FsNodeItemView`.

**Configuration Props:**
The component will accept the following optional props to handle page differences:
*   `breadcrumbs`: Optional component to render at the top.
*   `actionBar`: Optional component for the selection bar (Dashboard only).
*   `emptyState`: Optional component for empty directories (Dashboard only).
*   `header`: Optional component for a custom title/header (Share Detail).
*   `navigationHandler`: Callback or prop to handle specific routing logic for navigation.

## Phase 3: Page Refactoring
**Goal:** Replace legacy code with the new shared components.

1.  **Refactor `share_detail.js`**:
    * Import shared `FsNodeListView`.
    *   Pass `navigationHandler` for the Share URL.
    *   Pass `header` for "Files & Directories".
2.  **Refactor `dashboard.js`**:
    * Import shared `FsNodeListView`.
    *   Pass `breadcrumbs`, `actionBar`, and `emptyState` components.

## Phase 4: Cleanup & Verification
1.  Remove all redundant local logic from `dashboard.js` and `share_detail.js`.
2.  Verify that:
    *   Selection still clears on document click.
    *   Loading states display correctly.
    *   Error messages are consistent.
    *   Navigation targets remain correct for both pages.
