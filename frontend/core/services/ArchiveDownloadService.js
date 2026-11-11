import m from "mithril";

import { ArchiveJob } from "../models/ArchiveJob";

const JSON_HEADERS = { Accept: "application/json" };
const ARCHIVE_HEADERS = { Accept: "application/zip" };
const HTTP_GONE = 410;
const HTTP_NOT_FOUND = 404;

const DETAIL_KEYS = ["detail", "description", "message", "error"];

const formatDetail = (detail) => {
  if (Array.isArray(detail)) {
    return detail.join("; ");
  }
  if (detail && typeof detail === "object") {
    return Object.values(detail)
      .flatMap((value) => (Array.isArray(value) ? value : [value]))
      .join("; ");
  }
  return String(detail);
};

/**
 * Turn a Mithril request error into text suitable for the waiting view.
 */
export const describeArchiveError = (error) => {
  if (!error) {
    return "Could not prepare the archive. Please try again.";
  }

  if (error.code === HTTP_GONE) {
    return (
      "This archive is no longer available. "
      + "The directory may have been deleted or the archive expired."
    );
  }

  const { response } = error;
  if (response && typeof response === "object") {
    for (const key of DETAIL_KEYS) {
      if (response[key]) {
        return formatDetail(response[key]);
      }
    }
  }
  if (typeof response === "string" && response) {
    return response;
  }

  if (error.code === HTTP_NOT_FOUND) {
    return (
      "This archive is no longer available. "
      + "The directory may have been deleted or the archive expired."
    );
  }

  return error.message || "Could not prepare the archive. Please try again.";
};

/**
 * Backend-facing archive job operations.
 *
 * ``start`` creates a new snapshot job; ``status`` refreshes an existing one.
 * Both return an ``ArchiveJob`` and never keep UI state.
 */
export const ArchiveDownloadService = {
  start(downloadUrl) {
    if (!downloadUrl) {
      return Promise.reject(new Error("Archive download URL is missing."));
    }

    return m
      .request(downloadUrl, {
        method: "GET",
        params: { format: "json" },
        headers: JSON_HEADERS,
      })
      .then((data) => new ArchiveJob(data));
  },

  status(statusUrl) {
    if (!statusUrl) {
      return Promise.reject(new Error("Archive status URL is missing."));
    }

    return m
      .request(statusUrl, {
        method: "GET",
        headers: JSON_HEADERS,
      })
      .then((data) => new ArchiveJob(data));
  },

  /**
   * Check that a ready archive can still be downloaded.
   *
   * The SPA navigates to ``file_url`` to let the browser handle large files.
   * A ``HEAD`` preflight keeps ``410``/``404`` responses inside the modal
   * instead of replacing the whole page with a JSON error document.
   */
  checkFile(fileUrl) {
    if (!fileUrl) {
      return Promise.reject(new Error("Archive file URL is missing."));
    }

    return m
      .request(fileUrl, {
        method: "HEAD",
        headers: ARCHIVE_HEADERS,
      })
      .then(() => true);
  },
};
