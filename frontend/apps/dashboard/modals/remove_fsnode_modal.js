import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import { API_V1_FSNODE_BY_ID } from "../constants/endpoints";
import Button from "@polyfile/core/ui-kit/button";
import {DashboardFsNodeList} from "../services/DashboardFsNodeList";
import { getApiErrorDetail } from "./errors";
import m from "mithril";


const sendRequest = (vnode) => {
  vnode.state.error = null;
  if (!vnode.state.removeList || vnode.state.removeList.length === 0) {
    return Promise.resolve();
  }

  const permanent = Boolean(vnode.state.permanent);

  // Delete by UUID: permanent items get 202 Accepted, trashed items 200.
  const requests = vnode.state.removeList.map((item) =>
    m.request(m.buildPathname(API_V1_FSNODE_BY_ID, { id: item.id }), {
      method: "DELETE",
      ...(permanent ? { params: { permanent: "true" } } : {}),
    }),
  );

  return Promise.allSettled(requests).then((results) => {
    const rejected = results.find((result) => result.status === "rejected");
    if (rejected) {
      // Keep the modal open and surface the first failure.
      vnode.state.error = rejected.reason;
      return;
    }

    closeModal(vnode.attrs.modalId);
    // Remove only the successfully deleted items
    const toRemove = new Set(vnode.state.removeList);
    DashboardFsNodeList.elements = DashboardFsNodeList.elements.filter(
      (item) => !toRemove.has(item),
    );
  });
}

const RemoveFsNodeModalComponent = {
  oninit(vnode) {
    vnode.state.error = null;
    vnode.state.permanent = false;
    vnode.state.removeList = DashboardFsNodeList.elements.filter(item => item.selected);
  },

  view(vnode) {
    const permanent = Boolean(vnode.state.permanent);
    const count = vnode.state.removeList.length;
    const label = permanent ? "Delete permanently" : "Move to Trash";

    return (
      m(Modal, vnode.attrs,
        m(".modal-dialog",
          m(".modal-content", [
            m(Modal.modalHeader, {title: "Remove?", ...vnode.attrs}),
            m("form.has-validation", {
              onsubmit: (e) => {
                e.preventDefault();
                return sendRequest(vnode);
              },
            }, [
              m(".modal-body", [
                vnode.state.error && m(".alert alert-danger", getApiErrorDetail(vnode.state.error)),
                permanent
                  ? m("p", `${count === 1 ? "This item" : "These items"} will be deleted immediately and forever. Items already in the Trash will stay in the Trash. This cannot be undone.`)
                  : m("p", `${count === 1 ? "This item" : "These items"} will be moved to the Trash and kept for 30 days. You can restore them later.`),
                m(".form-check", [
                  m("input.form-check-input[type=checkbox][id=permanent-delete]", {
                    checked: permanent,
                    onchange: (e) => { vnode.state.permanent = e.target.checked; },
                  }),
                  m("label.form-check-label[for=permanent-delete]", "Delete permanently, bypassing the Trash"),
                ]),
              ]),
              m(".modal-footer", [
                m(Button, { type: "button", class: "btn-secondary", onclick: () => {closeModal(vnode.attrs.modalId)}}, "Cancel"),
                m(Button, { type: "submit", class: permanent ? "btn-danger" : "btn-primary" }, label),
              ]),
            ]),
          ])
        )
      )
    )
  }
};

export { RemoveFsNodeModalComponent, sendRequest as sendRemoveFsNodesRequest };
