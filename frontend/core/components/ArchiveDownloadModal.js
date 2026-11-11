import m from "mithril";

import { Modal, closeModal } from "../../apps/dashboard/bootstrap/modal";
import { PERCENT_MAX } from "../models/ArchiveJob";
import {
  ArchiveDownloadService,
  describeArchiveError,
} from "../services/ArchiveDownloadService";
import Button from "../ui-kit/button";

const FALLBACK_RETRY_DELAY_MS = 2000;
const BYTES_PER_UNIT = 1024;
const HTTP_GONE = 410;
const HTTP_NOT_FOUND = 404;

const stopPolling = (state) => {
  if (state.timer !== null) {
    clearTimeout(state.timer);
    state.timer = null;
  }
};

const triggerDownload = (url) => {
  if (!url || typeof window === "undefined" || !window.location) {
    return false;
  }
  window.location.assign(url);
  return true;
};

const formatBytes = (value) => {
  if (!value) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(
    units.length - 1,
    Math.floor(Math.log(value) / Math.log(BYTES_PER_UNIT)),
  );
  return `${(value / (BYTES_PER_UNIT ** exponent)).toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`;
};

/**
 * Modal that starts an asynchronous directory archive and polls its status.
 *
 * The job is created on open (or when the user retries), so every retry builds
 * a fresh snapshot instead of reusing an expired archive.
 */
export const ArchiveDownloadModal = {
  oninit(vnode) {
    vnode.state.job = null;
    vnode.state.error = "";
    vnode.state.downloaded = false;
    vnode.state.timer = null;
    vnode.state.closed = false;
    vnode.state.requestId = 0;
    this.start(vnode);
  },

  onremove(vnode) {
    vnode.state.closed = true;
    stopPolling(vnode.state);
  },

  start(vnode) {
    stopPolling(vnode.state);
    vnode.state.job = null;
    vnode.state.error = "";
    vnode.state.downloaded = false;
    vnode.state.requestId += 1;
    const { requestId } = vnode.state;

    ArchiveDownloadService.start(vnode.attrs.downloadUrl)
      .then((job) => {
        if (requestId === vnode.state.requestId) {
          this.applyJob(vnode, job);
        }
      })
      .catch((error) => {
        if (requestId === vnode.state.requestId && !vnode.state.closed) {
          vnode.state.error = describeArchiveError(error);
        }
      });
  },

  applyJob(vnode, job) {
    if (vnode.state.closed) {
      return;
    }

    vnode.state.job = job;
    vnode.state.error = "";

    if (job.is_ready) {
      stopPolling(vnode.state);
      this.download(vnode, job);
      return;
    }

    if (job.has_failed || job.is_terminal) {
      stopPolling(vnode.state);
      vnode.state.error = job.error_message;
      return;
    }

    this.schedulePoll(vnode);
  },

  /**
   * Verify the archive file before navigating to it.
   *
   * A deleted or expired archive answers ``410``; navigating directly would
   * replace the SPA with a raw JSON error page, so the check happens first and
   * failures stay inside the modal.
   */
  download(vnode, job = vnode.state.job) {
    if (vnode.state.closed || !job?.is_ready) {
      return;
    }

    const { requestId } = vnode.state;
    vnode.state.downloaded = false;

    ArchiveDownloadService.checkFile(job.file_url)
      .then(() => {
        if (vnode.state.closed || requestId !== vnode.state.requestId) {
          return;
        }
        vnode.state.downloaded = triggerDownload(job.file_url);
      })
      .catch((error) => {
        if (vnode.state.closed || requestId !== vnode.state.requestId) {
          return;
        }
        vnode.state.downloaded = false;
        vnode.state.error = describeArchiveError(error);
      });
  },

  schedulePoll(vnode) {
    if (vnode.state.closed) {
      return;
    }
    stopPolling(vnode.state);
    const delay = vnode.state.job?.retry_delay_ms || FALLBACK_RETRY_DELAY_MS;
    vnode.state.timer = setTimeout(() => this.poll(vnode), delay);
  },

  poll(vnode) {
    if (vnode.state.closed) {
      return;
    }

    const statusUrl = vnode.state.job?.status_url;
    if (!statusUrl) {
      vnode.state.error = "The archive status is not available. Please try again.";
      return;
    }

    const { requestId } = vnode.state;
    ArchiveDownloadService.status(statusUrl)
      .then((job) => {
        if (requestId === vnode.state.requestId) {
          this.applyJob(vnode, job);
        }
      })
      .catch((error) => {
        if (vnode.state.closed || requestId !== vnode.state.requestId) {
          return;
        }

        vnode.state.error = describeArchiveError(error);
        if (error?.code === HTTP_GONE || error?.code === HTTP_NOT_FOUND) {
          stopPolling(vnode.state);
          return;
        }
        vnode.state.timer = setTimeout(
          () => this.poll(vnode),
          FALLBACK_RETRY_DELAY_MS,
        );
      });
  },

  renderProgress(vnode) {
    const { job } = vnode.state;
    const percent = job?.progress_percent;
    const indeterminate = percent === null || typeof percent === "undefined";

    return m(".mb-3", [
      m(".progress", [
        m(".progress-bar", {
          class: indeterminate ? "progress-bar-striped progress-bar-animated" : "",
          style: `width: ${indeterminate ? PERCENT_MAX : percent}%`,
          role: "progressbar",
          "aria-valuenow": indeterminate ? null : percent,
          "aria-valuemin": 0,
          "aria-valuemax": PERCENT_MAX,
        }),
      ]),
      m(
        "p.text-muted.mb-0.mt-2",
        job
          ? `${job.processed_files} of ${job.total_files} files processed `
            + `(${formatBytes(job.processed_bytes)} of ${formatBytes(job.total_bytes)})`
          : "Starting the archive...",
      ),
    ]);
  },

  renderBody(vnode) {
    const { job, error, downloaded } = vnode.state;

    return m(".modal-body", [
      error && m(".alert.alert-danger", { role: "alert" }, error),
      downloaded && m(".alert.alert-success", "Your download has started."),
      !error && job?.is_ready && !downloaded && m(
        "p",
        m(
          "a",
          {
            href: job.file_url,
            onclick: (event) => {
              event.preventDefault();
              this.download(vnode, job);
            },
          },
          "Download archive",
        ),
      ),
      !error && !downloaded && this.renderProgress(vnode),
    ]);
  },

  view(vnode) {
    const { modalId } = vnode.attrs;
    const title = vnode.state.job?.root_node_name
      ? `Preparing "${vnode.state.job.root_node_name}"`
      : "Preparing archive";

    return m(
      Modal,
      vnode.attrs,
      m(
        ".modal-dialog",
        m(".modal-content", [
          m(Modal.modalHeader, { ...vnode.attrs, title }),
          this.renderBody(vnode),
          m(".modal-footer", [
            vnode.state.error && m(
              Button,
              {
                type: "button",
                class: "btn-primary",
                onclick: () => this.start(vnode),
              },
              "Try again",
            ),
            m(
              Button,
              {
                type: "button",
                class: "btn-secondary",
                onclick: () => closeModal(modalId),
              },
              "Close",
            ),
          ]),
        ]),
      ),
    );
  },
};
