import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import { API_V1_FSNODE } from "../constants/endpoints";
import Button from "@polyfile/core/ui-kit/button";
import {joinPath} from "@polyfile/core/utils/urls";
import {DashboardFsNodeList} from "../services/DashboardFsNodeList";
import m from "mithril";


const getDetailFromError = (error) => {
  if (error.code === 0 || error.response === null) {
    return "Unknown error, please try again later";
  }
  if (Object.hasOwn(error.response, "detail")) {
    if (Array.isArray(error.response.detail)) {
      return error.response.detail.join("; ");
    } 
    return String(error.response.detail);
  }
  return "";
};

const sendRequest = (vnode) => {
  vnode.state.error = null;
  if (!vnode.state.removeList || vnode.state.removeList.length === 0) {
    return Promise.resolve();
  }

  const paths = vnode.state.removeList.map((item) =>
    joinPath(DashboardFsNodeList.current.path, item.name),
  );

  // For MVP delete sequentially; all return 202 Accepted
  const requests = paths.map((path) =>
    m.request(API_V1_FSNODE, {
      method: "DELETE",
      params: { path },
    }),
  );

  return Promise.allSettled(requests).then((results) => {
    closeModal(vnode.attrs.modalId);
    // Optimistically remove all requested items
    const toRemove = new Set(vnode.state.removeList);
    DashboardFsNodeList.elements = DashboardFsNodeList.elements.filter(
      (item) => !toRemove.has(item),
    );
  }, (error) => {
    vnode.state.error = error;
  });
}

const RemoveFsNodeModalComponent = {
  oninit(vnode) {
    vnode.state.error = null;
    vnode.state.removeList = DashboardFsNodeList.elements.filter(item => item.selected);
  },

  view(vnode) {
    return (
      m(Modal, vnode.attrs,
        m(".modal-dialog",
          m(".modal-content", [
            m(Modal.modalHeader, {title: "Remove?", ...vnode.attrs}),
            m("form.has-validation", {
              onsubmit: (e) => {e.preventDefault(); sendRequest(vnode)},
            }, [
              m(".modal-body", [
                vnode.state.error && m(".alert alert-danger", getDetailFromError(vnode.state.error)),
                m("p", "This file will be removed"),
              ]),
              m(".modal-footer", [
                m(Button, { type: "button", class: "btn-secondary", onclick: () => {closeModal(vnode.attrs.modalId)}}, "Cancel"),
                m(Button, { type: "submit", class: "btn-danger" }, "Remove"),
              ]),
            ]),
          ])
        )
      )
    )
  }
};

export default RemoveFsNodeModalComponent;
