import m from "mithril";

import { Modal, closeModal } from "../bootstrap/modal";
import { UploadManager } from "../services/UploadManager";

const STATUS_LABELS = {
  idle: "No uploads",
  uploading: "Uploading",
  stopped: "Upload stopped",
  done: "Upload complete",
  failed: "Upload failed",
};

const STATUS_CLASSES = {
  failed: "bg-danger",
  uploading: "bg-success",
  done: "bg-success",
  stopped: "bg-secondary",
  idle: "bg-secondary",
};
const BYTES_PER_UNIT = 1024;
const PERCENT_MAX = 100;

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

const getManager = (vnode) => vnode.attrs.manager || UploadManager;

const stopPropagation = (event) => {
  event.stopPropagation();
};

// The actions menu is rendered with fixed positioning.
// Neither the panel nor the modal can clip it.
// The estimate only decides whether the menu opens up or down.
const MENU_GAP = 6;
const MENU_HEIGHT = 56;
const MENU_MARGIN = 8;

const actionsMenuStyle = (rect) => {
  if (!rect || typeof window === "undefined") {
    return "";
  }

  const openUp = rect.bottom + MENU_GAP + MENU_HEIGHT > window.innerHeight - MENU_MARGIN;
  const top = openUp
    ? rect.top - MENU_GAP - MENU_HEIGHT
    : rect.bottom + MENU_GAP;
  const right = Math.max(MENU_MARGIN, window.innerWidth - rect.right);

  return `top: ${Math.max(MENU_MARGIN, top)}px; right: ${right}px;`;
};

const toggleActionsMenu = (vnode, event) => {
  stopPropagation(event);
  vnode.state.menuOpen = !vnode.state.menuOpen;
  if (vnode.state.menuOpen) {
    vnode.state.menuStyle = actionsMenuStyle(
      event.currentTarget.getBoundingClientRect(),
    );
  }
};

const closeActionsMenu = (vnode, event) => {
  if (event) {
    stopPropagation(event);
  }
  vnode.state.menuOpen = false;
};

const jobPercent = (job) => {
  if (job.status === "done") {
    return PERCENT_MAX;
  }
  if (!job.size) {
    return 0;
  }
  return Math.min(
    PERCENT_MAX,
    Math.round(((job.loaded || 0) / job.size) * PERCENT_MAX),
  );
};

const isFailedJob = (job) => job.status === "error" || job.status === "conflict";

const jobErrorText = (job) => {
  if (job.status === "conflict") {
    return job.error?.existingType === "directory"
      ? "directory already exists"
      : "file already exists";
  }
  if (job.error?.code === 0) {
    return "network error";
  }
  return job.error?.detail || "upload failed";
};

const jobStatusText = (job) => {
  if (isFailedJob(job)) {
    return jobErrorText(job);
  }
  if (job.status === "canceled") {
    return "Canceled";
  }
  return `${jobPercent(job)}%`;
};

const errorMessage = (job) => {
  if (job.status === "conflict") {
    return job.error?.existingType === "directory"
      ? `A directory named "${job.name}" already exists in this folder.`
      : `File "${job.name}" already exists in this folder. Replace it?`;
  }
  if (job.error?.code === 0) {
    return `Could not upload "${job.name}". Check your connection.`;
  }
  return job.error?.detail || `Could not upload "${job.name}".`;
};

const collapseIcon = (collapsed) => (collapsed ? "fa-chevron-up" : "fa-chevron-down");

const actionButton = (label, className, onClick) => m(
  `button.btn.btn-sm.${className}`,
  {
    type: "button",
    onclick: (event) => {
      stopPropagation(event);
      onClick();
    },
  },
  label,
);

const UploadMonitorHeader = {
  oninit(vnode) {
    vnode.state.menuOpen = false;
    vnode.state.menuStyle = "";
  },

  view(vnode) {
    const manager = getManager(vnode);
    const modal = vnode.attrs.mode === "modal";
    const { status } = manager;
    const showPercent = status !== "idle";

    if (!manager.hasPendingWork) {
      vnode.state.menuOpen = false;
    }

    return m(
      ".upload-monitor__header.modal-header.border-0",
      {
        class: `${STATUS_CLASSES[status] || "bg-secondary"} text-white`
          + `${modal ? " upload-monitor__header--modal" : ""}`,
        onclick: modal ? null : () => manager.toggle(),
      },
      [
        m(".upload-monitor__progress", { style: `width: ${manager.percent}%` }),
        m(".d-flex.align-items-center.gap-2.w-100.position-relative", [
          m(".flex-grow-1.min-width-0", [
            m(".fw-semibold.text-truncate", STATUS_LABELS[status] || STATUS_LABELS.idle),
            showPercent && m(
              ".small.text-white-50",
              `${manager.percent}% · ${manager.completedCount}/${manager.totalCount} files`,
            ),
          ]),
          manager.hasPendingWork && m(
            "button.upload-monitor__actions-toggle.btn.btn-sm.btn-link.text-white.p-1",
            {
              type: "button",
              "aria-label": "Upload actions",
              "aria-haspopup": "menu",
              "aria-expanded": vnode.state.menuOpen ? "true" : "false",
              onclick: (event) => toggleActionsMenu(vnode, event),
            },
            m("span.fa.fa-ellipsis-vertical[aria-hidden=true]"),
          ),
          !modal && m(
            "button.upload-monitor__collapse.btn.btn-sm.btn-link.text-white.p-1",
            {
              type: "button",
              title: manager.collapsed ? "Expand" : "Collapse",
              "aria-label": manager.collapsed ? "Expand" : "Collapse",
              "aria-expanded": manager.collapsed ? "false" : "true",
              onclick: (event) => {
                stopPropagation(event);
                manager.toggle();
              },
            },
            m(
              `span.fa.${collapseIcon(manager.collapsed)}[aria-hidden=true]`,
            ),
          ),
          (modal || manager.isFinished) && m(
            "button.upload-monitor__close.btn.btn-sm.btn-link.text-white.p-1",
            {
              type: "button",
              title: "Close",
              "aria-label": "Close",
              onclick: (event) => {
                stopPropagation(event);
                if (modal) {
                  closeModal(vnode.attrs.modalId);
                  return;
                }
                manager.close();
              },
            },
            m("span.fa.fa-xmark[aria-hidden=true]"),
          ),
        ]),
        manager.hasPendingWork && vnode.state.menuOpen && [
          m(".upload-monitor__menu-backdrop", {
            onclick: (event) => closeActionsMenu(vnode, event),
          }),
          m("ul.upload-monitor__menu.dropdown-menu.show", {
            style: vnode.state.menuStyle,
            onclick: stopPropagation,
          }, [
            m("li", m(
              "button.dropdown-item",
              {
                type: "button",
                onclick: (event) => {
                  closeActionsMenu(vnode, event);
                  manager.cancelAll();
                },
              },
              "Cancel all uploads",
            )),
          ]),
        ],
      ],
    );
  },
};

const renderFirstError = (manager) => {
  const job = manager.firstError;
  if (!job) {
    return null;
  }

  const directoryConflict = job.status === "conflict"
    && job.error?.existingType === "directory";
  const canRetry = job.status === "error" && job.error?.retryable;
  const message = errorMessage(job);

  return m(".alert.alert-danger.mb-3.py-2", [
    m("div", message),
    m(".d-flex.gap-2.mt-2", [
      job.status === "conflict" && !directoryConflict
        && actionButton("Replace", "btn-danger", () => manager.replace(job)),
      canRetry && actionButton("Retry", "btn-danger", () => manager.retry(job)),
      actionButton("Don't upload", "btn-outline-danger", () => manager.skip(job)),
    ]),
  ]);
};

const renderJob = (job) => m(
  ".upload-monitor__job.d-flex.align-items-start.gap-2.border-bottom",
  { key: job.id },
  [
    m(".flex-grow-1.min-width-0", [
      m(".text-truncate", { title: job.name }, job.name),
      m(".small.text-secondary", formatBytes(job.size)),
    ]),
    m(
      ".small.flex-shrink-0.text-end.upload-monitor__job-status",
      { class: isFailedJob(job) ? "text-danger" : "text-secondary" },
      jobStatusText(job),
    ),
  ],
);

const UploadMonitorBody = {
  view(vnode) {
    const manager = getManager(vnode);
    const modal = vnode.attrs.mode === "modal";

    return m(
      ".upload-monitor__body",
      { class: modal ? "modal-body" : "" },
      [
        renderFirstError(manager),
        manager.jobs.length === 0
          ? m(".text-secondary.py-3", "No uploads")
          : m(".upload-monitor__list", manager.jobs.map(renderJob)),
      ],
    );
  },
};

/**
 * Panel docked to the bottom-right corner on desktop, without a backdrop.
 */
export const UploadMonitorDocked = {
  view(vnode) {
    const manager = getManager(vnode);
    if (!manager.visible) {
      return null;
    }

    return m(".upload-monitor.d-none.d-md-flex.flex-column", [
      m(UploadMonitorHeader, { manager, mode: "docked" }),
      !manager.collapsed && m(UploadMonitorBody, { manager, mode: "docked" }),
    ]);
  },
};

/**
 * Standard modal used by the mobile navbar button.
 */
export const UploadMonitorModal = {
  backdrop: true,

  view(vnode) {
    const manager = getManager(vnode);

    return m(
      Modal,
      vnode.attrs,
      m(
        ".modal-dialog.modal-dialog-scrollable",
        m(".modal-content", [
          m(UploadMonitorHeader, {
            manager,
            mode: "modal",
            modalId: vnode.attrs.modalId,
          }),
          m(UploadMonitorBody, { manager, mode: "modal" }),
        ]),
      ),
    );
  },
};
