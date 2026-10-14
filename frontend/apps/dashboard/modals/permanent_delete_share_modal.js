import m from "mithril";
import { Modal, closeModal, showModal } from "../bootstrap/modal";
import Button from "@polyfile/core/ui-kit/button";

const PermanentDeleteShareModal = {
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
    const { share, onConfirm } = vnode.attrs;

    (onConfirm ? onConfirm(share) : Promise.resolve())
      .then(() => {
        closeModal(vnode.attrs.modalId);
      })
      .catch((error) => {
        const detail = error?.response?.detail;
        if (typeof detail === "string") {
          vnode.state.error = detail;
        } else if (Array.isArray(detail)) {
          vnode.state.error = detail.join("; ");
        } else if (detail && typeof detail === "object") {
          vnode.state.error = Object.values(detail).flat().join("; ");
        } else {
          vnode.state.error = error?.message || "Failed to delete the share.";
        }
      })
      .finally(() => {
        vnode.state.loading = false;
      });
  },

  renderFooter(vnode) {
    return m(".modal-footer", [
      m(Button, {
        type: "button",
        class: "btn-secondary",
        onclick: () => closeModal(vnode.attrs.modalId),
      }, "Cancel"),
      m(Button, {
        type: "submit",
        class: "btn-danger",
        disabled: vnode.state.loading,
      }, "Delete permanently"),
    ]);
  },

  view(vnode) {
    const { share } = vnode.attrs;
    const name = share?.root_fs_node?.name || share?.id || "this share";

    return m(
      Modal,
      vnode.attrs,
      m(
        ".modal-dialog",
        m(".modal-content", [
          m(Modal.modalHeader, { ...vnode.attrs, title: "Delete public link permanently" }),
          m(
            "form.has-validation",
            {
              onsubmit: (e) => {
                e.preventDefault();
                this.confirm(vnode);
              },
            },
            [
              m(".modal-body", [
                vnode.state.error && m(".alert alert-danger", vnode.state.error),
                m("p", `Are you sure you want to permanently delete "${name}"?`),
                m("p.text-danger", "This action cannot be undone and removes download history."),
              ]),
              this.renderFooter(vnode),
            ]
          ),
        ])
      )
    );
  },
};

export const showPermanentDeleteShareModal = (attrs) => showModal(PermanentDeleteShareModal, attrs);
export { PermanentDeleteShareModal };
