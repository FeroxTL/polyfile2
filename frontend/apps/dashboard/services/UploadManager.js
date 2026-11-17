import m from "mithril";

import { API_V1_FSNODE_BY_ID, API_V1_FSNODE_TOUCH } from "../constants/endpoints";
import { DashboardFsNode } from "../models/DashboardFsNode";
import { DashboardFsNodeList } from "./DashboardFsNodeList";

const TERMINAL_STATUSES = new Set(["done", "canceled"]);
const ACTIVE_UPLOAD_STATUSES = new Set(["queued", "creating", "uploading"]);
const STATUS_CONFLICT = "conflict";
const STATUS_ERROR = "error";
const REDRAW_FALLBACK_MS = 16;
const HTTP_CONFLICT = 409;
const HTTP_SERVER_ERROR = 500;
const PERCENT_MAX = 100;

let jobSequence = 0;
let redrawScheduled = false;

const scheduleRedraw = () => {
  // Logical unit tests run without a DOM; Mithril's redraw loop is unavailable.
  if (typeof window === "undefined" || redrawScheduled) {
    return;
  }
  redrawScheduled = true;
  const schedule = typeof requestAnimationFrame === "function"
    ? (callback) => requestAnimationFrame(callback)
    : (callback) => setTimeout(callback, REDRAW_FALLBACK_MS);
  schedule(() => {
    redrawScheduled = false;
    m.redraw();
  });
};

const serializeBody = (value) => value;

const normalizeDetail = (detail) => {
  if (Array.isArray(detail)) {
    return detail.join("; ");
  }
  if (detail && typeof detail === "object") {
    return Object.values(detail).flat().join("; ");
  }
  return typeof detail === "string" ? detail : "";
};

/**
 * Insert or replace an uploaded node in the currently displayed directory.
 *
 * @param {Object} job - Upload job owning the node.
 * @param {Object} data - FsNode payload returned by touch or upload.
 * @returns {DashboardFsNode} Node attached to the job.
 */
const upsertNode = (job, data) => {
  const list = DashboardFsNodeList;
  const sameParent = (list.current?.id ?? null) === job.parentId;
  const existing = sameParent
    ? list.elements.find((item) => item.id === data.id)
    : null;

  // A replacement reuses the existing FsNode.
  // The touch payload has no share field, so keep the existing node data.
  const node = new DashboardFsNode({
    ...(existing ? { share: existing.share } : {}),
    ...data,
    upload_status: "uploading",
  });

  if (sameParent) {
    if (existing) {
      list.elements[list.elements.indexOf(existing)] = node;
    } else {
      list.addFsNode(node);
    }
    list.selectFsNode(node);
  }

  return node;
};

const removeNodeFromList = (node) => {
  const index = DashboardFsNodeList.elements.indexOf(node);
  if (index >= 0) {
    DashboardFsNodeList.elements.splice(index, 1);
  }
};

/**
 * Remove a locally hidden node on the server.
 *
 * @param {DashboardFsNode} node - Node to delete.
 * @returns {Promise<void>}
 */
const deleteNode = async (node) => {
  removeNodeFromList(node);
  if (!node?.id) {
    return;
  }

  try {
    // Placeholder nodes of cancelled uploads must not pollute the Trash.
    await m.request(m.buildPathname(API_V1_FSNODE_BY_ID, { id: node.id }), {
      method: "DELETE",
      params: { permanent: "true" },
    });
  } catch {
    // The node is already hidden locally.
    // A failed cleanup is not actionable in the queue UI.
  }
};

/**
 * Convert an m.request rejection into the flat shape used by the upload UI.
 *
 * @param {Object|null} error - Rejection value from m.request.
 * @returns {Object} Normalized upload error.
 */
const parseRequestError = (error) => {
  const response = error?.response || {};
  const code = typeof error?.code === "number" ? error.code : 0;
  const errorId = response.error_id || "";
  const existingType = response.existing_type || null;

  return {
    code,
    errorId,
    detail: normalizeDetail(response.detail ?? response.message),
    existingNodeId: response.existing_node_id || null,
    existingType,
    retryable: code === 0 || code >= HTTP_SERVER_ERROR,
    isConflict: errorId === "FsNodeExistsError" || code === HTTP_CONFLICT,
  };
};

/**
 * Center of the upload pipeline.
 *
 * Files are uploaded one at a time. The queue pauses on the first unresolved
 * error so the modal can show exactly one actionable message.
 */
export class UploadManagerService {
  constructor() {
    this.jobs = [];
    this.active = null;
    this.visible = false;
    this.collapsed = false;
    this.stopped = false;
    this.stoppedPercent = 0;
  }

  /**
   * Clear all state. Intended for tests and for a fresh document load.
   *
   * @returns {void}
   */
  reset() {
    this.jobs = [];
    this.active = null;
    this.visible = false;
    this.collapsed = false;
    this.stopped = false;
    this.stoppedPercent = 0;
  }

  get hasActiveUploads() {
    return this.jobs.some((job) => ACTIVE_UPLOAD_STATUSES.has(job.status));
  }

  get hasPendingWork() {
    return this.jobs.some((job) => !TERMINAL_STATUSES.has(job.status));
  }

  get activeCount() {
    return this.jobs.filter((job) => !TERMINAL_STATUSES.has(job.status)).length;
  }

  get firstError() {
    return this.jobs.find(
      (job) => job.status === STATUS_CONFLICT || job.status === STATUS_ERROR,
    ) || null;
  }

  get isFinished() {
    return !this.hasPendingWork;
  }

  /**
   * Jobs that still count towards the overall progress.
   *
   * @returns {Object[]} All jobs except the canceled ones.
   */
  get progressJobs() {
    return this.jobs.filter((job) => job.status !== "canceled");
  }

  /**
   * Number of files finished successfully.
   *
   * @returns {number} Completed file count.
   */
  get completedCount() {
    return this.progressJobs.filter((job) => job.status === "done").length;
  }

  /**
   * Total number of files in the current batch.
   *
   * @returns {number} File count.
   */
  get totalCount() {
    return this.progressJobs.length;
  }

  /**
   * Bytes uploaded across the whole queue, including finished files.
   *
   * @returns {number} Uploaded bytes.
   */
  get uploadedSize() {
    return this.progressJobs.reduce(
      (sum, job) => sum + (job.status === "done"
        ? job.size
        : Math.min(job.loaded || 0, job.size)),
      0,
    );
  }

  /**
   * Total size of every file in the current batch.
   *
   * @returns {number} Total bytes.
   */
  get totalSize() {
    return this.progressJobs.reduce((sum, job) => sum + job.size, 0);
  }

  get status() {
    if (this.firstError) {
      return "failed";
    }
    if (this.hasActiveUploads) {
      return "uploading";
    }
    if (this.stopped) {
      return "stopped";
    }
    return this.jobs.length > 0 ? "done" : "idle";
  }

  /**
   * Overall byte progress of the whole queue, not of the active file.
   *
   * @returns {number} Percentage from 0 to 100.
   */
  get percent() {
    if (this.status === "stopped") {
      return this.stoppedPercent;
    }

    const jobs = this.progressJobs;
    if (jobs.length === 0) {
      return 0;
    }

    const total = this.totalSize;
    if (total === 0) {
      return jobs.every((job) => job.status === "done") ? PERCENT_MAX : 0;
    }

    return Math.min(
      PERCENT_MAX,
      Math.round((this.uploadedSize / total) * PERCENT_MAX),
    );
  }

  /**
   * Add files to the queue and make sure the panel is visible.
   *
   * @param {File[]|FileList} files - Files selected by the user.
   * @param {string|null} parentId - Target directory captured at selection time.
   * @returns {void}
   */
  enqueueFiles(files, parentId = null) {
    const selected = Array.from(files || []).filter(Boolean);
    if (selected.length === 0) {
      return;
    }

    if (this.jobs.every((job) => TERMINAL_STATUSES.has(job.status))) {
      this.jobs = [];
    }

    this.stopped = false;
    this.stoppedPercent = 0;
    this.visible = true;
    this.collapsed = false;

    selected.forEach((file) => {
      jobSequence += 1;
      this.jobs.push({
        id: `upload-${jobSequence}`,
        file,
        name: file.name || "file",
        size: Number(file.size) || 0,
        parentId,
        loaded: 0,
        status: "queued",
        error: null,
        node: null,
        uploadUrl: null,
        xhr: null,
        replace: false,
        createdNode: false,
      });
    });

    scheduleRedraw();
    this.startNext();
  }

  /**
   * Start the next queued file when the queue is not paused by an error.
   *
   * @returns {void}
   */
  startNext() {
    if (this.active || this.stopped || this.firstError) {
      scheduleRedraw();
      return;
    }

    const job = this.jobs.find((item) => item.status === "queued");
    if (!job) {
      this.active = null;
      scheduleRedraw();
      return;
    }

    this.active = job;
    this.runJob(job);
  }

  async runJob(job) {
    try {
      if (job.status === "canceled") {
        return;
      }

      if (!job.uploadUrl) {
        const created = await this.createUploadSession(job);
        if (!created || job.status === "canceled") {
          return;
        }
      }

      await this.uploadContent(job);
    } catch (error) {
      this.handleJobError(job, error);
    }
  }

  // The queue is a singleton; this step only mutates the passed job.
  // eslint-disable-next-line class-methods-use-this
  async createUploadSession(job) {
    job.status = "creating";
    job.error = null;

    const body = {
      parent_id: job.parentId,
      name: job.name,
    };
    if (job.replace) {
      body.replace = true;
    }

    const data = await m.request(API_V1_FSNODE_TOUCH, {
      method: "POST",
      body,
      config: (xhr) => {
        job.xhr = xhr;
        return xhr;
      },
    });

    // The request has completed; clear the abort handle without racing cancelAll.
    // eslint-disable-next-line require-atomic-updates
    job.xhr = null;
    if (job.status === "canceled") {
      return false;
    }

    const replacedNode = Boolean(job.replace);
    job.replace = false;
    job.uploadUrl = data.upload_url;
    job.createdNode = !replacedNode;
    job.node = upsertNode(job, data);
    return true;
  }

  async uploadContent(job) {
    job.status = "uploading";
    job.loaded = 0;
    if (job.node) {
      job.node.upload_status = "uploading";
    }

    const data = await m.request(job.uploadUrl, {
      method: "POST",
      body: job.file,
      serialize: serializeBody,
      config: (xhr) => {
        job.xhr = xhr;
        if (xhr?.upload) {
          xhr.upload.onprogress = (event) => {
            if (job.status !== "uploading") {
              return;
            }
            job.loaded = Number(event.loaded) || 0;
            scheduleRedraw();
          };
        }
        return xhr;
      },
    });

    // The request has completed; clear the abort handle without racing cancelAll.
    // eslint-disable-next-line require-atomic-updates
    job.xhr = null;
    if (job.status === "canceled") {
      return;
    }

    Object.assign(job.node, data);
    job.node.upload_status = "done";
    job.loaded = job.size;
    job.status = "done";
    job.uploadUrl = null;
    this.active = null;
    scheduleRedraw();
    this.startNext();
  }

  handleJobError(job, error) {
    job.xhr = null;
    if (job.status === "canceled") {
      return;
    }

    job.error = parseRequestError(error);
    job.status = job.error.isConflict ? STATUS_CONFLICT : STATUS_ERROR;
    if (job.node) {
      job.node.upload_status = "error";
    }
    this.active = null;
    scheduleRedraw();
  }

  /**
   * Retry a failed file. A failed content upload reuses its upload token.
   *
   * @param {Object} job - Failed job.
   * @returns {void}
   */
  retry(job) {
    if (!job || job.status !== STATUS_ERROR || !job.error?.retryable) {
      return;
    }

    job.status = "queued";
    job.error = null;
    job.loaded = 0;
    scheduleRedraw();
    this.startNext();
  }

  /**
   * Retry a conflicting file with `replace: true`.
   *
   * @param {Object} job - Job in the conflict state.
   * @returns {void}
   */
  replace(job) {
    if (
      !job
      || job.status !== STATUS_CONFLICT
      || job.error?.existingType === "directory"
    ) {
      return;
    }

    job.replace = true;
    job.status = "queued";
    job.error = null;
    job.uploadUrl = null;
    job.loaded = 0;
    scheduleRedraw();
    this.startNext();
  }

  /**
   * Drop a failed file and continue with the queue.
   *
   * @param {Object} job - Job to drop.
   * @returns {Promise<void>}
   */
  async skip(job) {
    if (!job) {
      return;
    }

    const index = this.jobs.indexOf(job);
    if (job.createdNode && job.node) {
      await deleteNode(job.node);
    } else if (job.node) {
      job.node.upload_status = "done";
    }

    if (index >= 0) {
      this.jobs.splice(index, 1);
    }
    if (this.active === job) {
      this.active = null;
    }
    scheduleRedraw();
    this.startNext();
  }

  /**
   * Abort every pending upload and delete placeholder nodes created by it.
   *
   * @returns {void}
   */
  cancelAll() {
    if (!this.hasPendingWork) {
      return;
    }

    this.stoppedPercent = this.percent;
    this.stopped = true;
    const nodesToDelete = [];

    this.jobs.forEach((job) => {
      if (TERMINAL_STATUSES.has(job.status)) {
        return;
      }

      if (job.xhr) {
        job.xhr.abort();
        job.xhr = null;
      }
      job.status = "canceled";
      job.error = null;

      if (job.node) {
        if (job.createdNode) {
          nodesToDelete.push(job.node);
        } else {
          job.node.upload_status = "done";
        }
      }
    });

    this.active = null;
    nodesToDelete.forEach((node) => {
      deleteNode(node);
    });
    scheduleRedraw();
  }

  toggle() {
    this.collapsed = !this.collapsed;
    scheduleRedraw();
  }

  close() {
    this.visible = false;
    if (this.isFinished) {
      this.jobs = [];
      this.stopped = false;
      this.stoppedPercent = 0;
    }
    scheduleRedraw();
  }
}

export const UploadManager = new UploadManagerService();

/**
 * Ask the browser to confirm leaving the page while uploads are pending.
 *
 * Browsers show their own generic dialog and ignore custom messages.
 * Only the fact that the event was canceled matters, not the returned text.
 *
 * @param {BeforeUnloadEvent} event - Native beforeunload event.
 * @returns {void}
 */
export const handleBeforeUnload = (event) => {
  if (!UploadManager.hasPendingWork) {
    return;
  }

  event.preventDefault();
  // Legacy browsers show the confirmation only for a non-empty value.
  event.returnValue = "";
};

if (typeof window !== "undefined") {
  window.addEventListener("beforeunload", handleBeforeUnload);
}

export { parseRequestError };
