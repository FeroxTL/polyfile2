import m from "mithril";

import { Modal, closeModal, showModal } from "../bootstrap/modal";
import Button from "@polyfile/core/ui-kit/button";

const STATUS_LABELS = {
  pending: "Waiting",
  restoring: "Restoring",
  conflict: "Name conflict",
  error: "Failed",
  done: "Restored",
  skipped: "Skipped",
};

const STATUS_CLASSES = {
  pending: "bg-secondary",
  restoring: "bg-primary",
  conflict: "bg-warning text-dark",
  error: "bg-danger",
  done: "bg-success",
  skipped: "bg-secondary",
};


/**
 * A restore monitor in the spirit of the upload monitor: entries are
 * processed one by one, and a name conflict pauses the queue so the user can
 * choose "Keep both" (rename) or "Skip".
 */
const RestoreMonitorModal = {
  oninit(vnode) {
    const entries = vnode.attrs.entries || [];
    vnode.state.jobs = entries.map((entry) => ({
      entry,
      status: "pending",
      error: null,
    }));
    vnode.state.running = false;
    vnode.state.stopped = false;
    vnode.state.notices = [];
    vnode.state.implicit = [];
  },

  findConflict(vnode) {
    return vnode.state.jobs.find((job) => job.status === "conflict") || null;
  },

  async processNext(vnode) {
    const job = this.findConflict(vnode) || vnode.state.jobs.find((item) => item.status === "pending");
    if (!job) {
      vnode.state.running = false;
      return false;
    }
    if (job.status === "conflict") {
      // Waiting for the user to resolve the conflict.
      vnode.state.running = false;
      return false;
    }

    const { service, onDone } = vnode.attrs;
    job.status = "restoring";
    job.error = null;
    try {
      const result = await service.restore(job.entry.id, "fail");
      job.status = "done";
      if (Array.isArray(result?.notices)) {
        vnode.state.notices.push(...result.notices);
      }
      if (Array.isArray(result?.restored_entries)) {
        vnode.state.implicit.push(...result.restored_entries);
      }
      if (onDone) {
        onDone(result);
      }
    } catch (error) {
      job.status = error?.response?.error_id === "FsNodeExistsError" ? "conflict" : "error";
      job.error = error;
      return job.status !== "conflict";
    }
    return true;
  },

  async run(vnode) {
    if (vnode.state.running || vnode.state.stopped) {
      return;
    }
    vnode.state.running = true;
    // eslint-disable-next-line no-await-in-loop
    while (await this.processNext(vnode)) {
      if (this.findConflict(vnode)) {
        break;
      }
    }
    // eslint-disable-next-line require-atomic-updates
    vnode.state.running = false;
  },

  async resolveConflict(vnode, onConflict) {
    const job = this.findConflict(vnode);
    if (!job || vnode.state.running) {
      return;
    }
    const { service, onDone } = vnode.attrs;
    job.status = "restoring";
    job.error = null;
    try {
      const result = await service.restore(job.entry.id, onConflict);
      job.status = onConflict === "rename" ? "done" : "skipped";
      if (Array.isArray(result?.notices)) {
        vnode.state.notices.push(...result.notices);
      }
      if (Array.isArray(result?.restored_entries)) {
        vnode.state.implicit.push(...result.restored_entries);
      }
      if (onDone) {
        onDone(result);
      }
    } catch (error) {
      job.status = "error";
      job.error = error;
    }
    this.run(vnode);
  },

  stop(vnode) {
    vnode.state.stopped = true;
  },

  isFinished(vnode) {
    return vnode.state.jobs.every((job) => ["done", "error", "skipped"].includes(job.status));
  },

  renderConflict(vnode, job) {
    return m(".alert.alert-warning.py-2", [
      m("div", `"${job.entry.name}" already exists. Keep both or skip this entry?`),
      m(".mt-2.d-flex.gap-2", [
        m(Button, {
          type: "button",
          class: "btn-sm btn-primary",
          onclick: () => this.resolveConflict(vnode, "rename"),
        }, "Keep both"),
        m(Button, {
          type: "button",
          class: "btn-sm btn-outline-secondary",
          onclick: () => this.resolveConflict(vnode, "skip"),
        }, "Skip"),
      ]),
    ]);
  },

  view(vnode) {
    const { jobs, notices, implicit } = vnode.state;
    const conflict = this.findConflict(vnode);
    const finished = this.isFinished(vnode);
    const implicitNames = implicit.map((entry) => entry.name).filter(Boolean);

    return m(
      Modal,
      vnode.attrs,
      m(".modal-dialog.modal-dialog-scrollable", m(".modal-content", [
        m(Modal.modalHeader, { ...vnode.attrs, title: "Restore from Trash" }),
        m(".modal-body", [
          m("ul.list-group", jobs.map((job) => m("li.list-group-item", [
            m("div.d-flex.justify-content-between.align-items-center", [
              m("span", m("i.fa[aria-hidden=true]", {
                class: job.entry.type === "directory" ? "fa-folder" : "fa-file",
              }), " ", job.entry.name),
              m("span.badge", {
                class: STATUS_CLASSES[job.status] || "bg-secondary",
              }, STATUS_LABELS[job.status] || job.status),
            ]),
            job.status === "conflict" && this.renderConflict(vnode, job),
            job.status === "error" && m(".small.text-danger", job.error?.message || "Restore failed"),
          ]))),
          implicitNames.length > 0 && m("p.text-muted.small.mt-3", `Also restored: ${implicitNames.join(", ")}`),
          notices.length > 0 && m("p.text-muted.small", notices.map((notice) => (
            `${notice.type === "merged" ? "Merged into" : "Renamed to"} "${notice.name}"`
          )).join("; ")),
        ]),
        m(".modal-footer", [
          !finished && !conflict && m(Button, {
            type: "button",
            class: "btn-secondary",
            onclick: () => this.stop(vnode),
          }, "Stop"),
          (finished || conflict) && m(Button, {
            type: "button",
            class: "btn-primary",
            onclick: () => closeModal(vnode.attrs.modalId),
          }, "Close"),
        ]),
      ]))
    );
  },

  oncreate(vnode) {
    this.run(vnode);
  },
};

export const showRestoreMonitorModal = (attrs) => showModal(RestoreMonitorModal, attrs);
export { RestoreMonitorModal };
