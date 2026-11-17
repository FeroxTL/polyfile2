import m from "mithril";

import { Modal, closeModal, showModal } from "../bootstrap/modal";
import Button from "@polyfile/core/ui-kit/button";

const getErrorDetail = (error) => {
  const detail = error?.response?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.join("; ");
  }
  if (detail && typeof detail === "object") {
    return Object.values(detail).flat().join("; ");
  }
  return error?.message || "Failed to delete the trash entries.";
};

const TrashConfirmModal = {
  oninit(vnode) {
    vnode.state.loading = false;
    vnode.state.error = null;
  },

  confirm(vnode) {
    if (vnode.state.loading) {
      return;
    }
    vnode.state.loading = true;
    vnode.state.error = null;

    const { entries = [], onConfirm } = vnode.attrs;
    (onConfirm ? onConfirm(entries) : Promise.resolve())
      .then(() => closeModal(vnode.attrs.modalId))
      .catch((error) => {
        vnode.state.error = getErrorDetail(error);
      })
      .finally(() => {
        vnode.state.loading = false;
      });
  },

  view(vnode) {
    const { title, message, confirmLabel, entries = [] } = vnode.attrs;
    const count = entries.length;
    const withFolders = entries.some((entry) => entry.type === "directory");

    return m(
      Modal,
      vnode.attrs,
      m(".modal-dialog", m(".modal-content", [
        m(Modal.modalHeader, { ...vnode.attrs, title: title || "Delete permanently" }),
        m("form.has-validation", {
          onsubmit: (event) => {
            event.preventDefault();
            this.confirm(vnode);
          },
        }, [
          m(".modal-body", [
            vnode.state.error && m(".alert alert-danger", vnode.state.error),
            m("p", message || (
              count > 1
                ? `Permanently delete ${count} entries from the Trash?`
                : "Permanently delete this entry from the Trash?"
            )),
            m("p.text-danger", "This cannot be undone. Trash entries inside selected folders will stay in the Trash."),
            withFolders && m("p.text-muted.small", "Folders will be hidden and their non-trashed content deleted forever."),
          ]),
          m(".modal-footer", [
            m(Button, {
              type: "button",
              class: "btn-secondary",
              onclick: () => closeModal(vnode.attrs.modalId),
            }, "Cancel"),
            m(Button, {
              type: "submit",
              class: "btn-danger",
              disabled: vnode.state.loading,
            }, confirmLabel || "Delete permanently"),
          ]),
        ]),
      ]))
    );
  },
};

export const showTrashConfirmModal = (attrs) => showModal(TrashConfirmModal, attrs);
export { TrashConfirmModal };
