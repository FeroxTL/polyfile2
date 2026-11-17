import m from "mithril";

import {
  API_V1_TRASH,
  API_V1_TRASH_EMPTY,
  API_V1_TRASH_ENTRY,
  API_V1_TRASH_RESTORE,
} from "../constants/endpoints";

const request = (url, options) => m.request(url, options);

/**
 * State and actions for the trash view.
 *
 * Entries are the objects the user actually deleted (trash roots). Nested
 * files of a trashed directory are not listed and cannot be inspected.
 */
export class TrashListService {
  constructor() {
    this.entries = [];
    this.selected = new Set();
    this.isLoading = false;
    this.error = null;
  }

  load() {
    this.isLoading = true;
    this.error = null;

    return request(API_V1_TRASH, { method: "GET" })
      .then((data) => {
        this.entries = Array.isArray(data?.entries) ? data.entries : [];
        this.selected.clear();
        this.error = null;
        return data;
      })
      .catch((error) => {
        this.error = error;
        throw error;
      })
      .finally(() => {
        this.isLoading = false;
      });
  }

  getSelectedEntries() {
    return this.entries.filter((entry) => this.selected.has(entry.id));
  }

  toggleSelected(entryId) {
    if (this.selected.has(entryId)) {
      this.selected.delete(entryId);
    } else {
      this.selected.add(entryId);
    }
  }

  clearSelected() {
    this.selected.clear();
  }

  /** Restore one entry; returns the backend response (node/notices). */
  restore(entryId, onConflict = "fail") {
    return request(m.buildPathname(API_V1_TRASH_RESTORE, { id: entryId }), {
      method: "POST",
      body: { on_conflict: onConflict },
    }).then((data) => {
      this.entries = this.entries.filter((entry) => entry.id !== entryId);
      this.selected.delete(entryId);
      return data;
    });
  }

  /** Permanently delete one entry from the trash. */
  deletePermanent(entryId) {
    return request(m.buildPathname(API_V1_TRASH_ENTRY, { id: entryId }), {
      method: "DELETE",
    }).then((data) => {
      this.entries = this.entries.filter((entry) => entry.id !== entryId);
      this.selected.delete(entryId);
      return data;
    });
  }

  /** Purge every entry in the trash. */
  empty() {
    return request(API_V1_TRASH_EMPTY, { method: "POST" }).then((data) => {
      this.entries = [];
      this.selected.clear();
      return data;
    });
  }
}

export const TrashList = new TrashListService();
