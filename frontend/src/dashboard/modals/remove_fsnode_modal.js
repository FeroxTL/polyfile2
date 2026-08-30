import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import { API_V1_FSNODE } from "../urls";
import Button from "../bootstrap/button";
import {
  FsNodeList,
} from "../dashboard";
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

  return m.request(API_V1_FSNODE, {
    method: "DELETE",
    // TODO: really remove only first?
    params: { path: `${FsNodeList.current.path  }/${  vnode.state.removeList[0].name}` },
  }).then(() => {
    closeModal(vnode.attrs.modalId);
    FsNodeList.elements = FsNodeList.elements.filter((item) => item !== vnode.state.removeList[0]);
  }, (error) => {
    vnode.state.error = error;
  });
}

const RemoveFsNodeModalComponent = {
  oninit(vnode) {
    vnode.state.error = null;
    vnode.state.removeList = FsNodeList.elements.filter(item => item.selected);
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
