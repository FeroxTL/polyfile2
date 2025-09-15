import m from "mithril";
import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import {
  FsNodeList,
} from "../dashboard";
import { API_V1_FSNODE } from "../urls";
import Button from "../bootstrap/button";


function getDetailFromError(error) {
  if (error.code == 0 || error.response == null) {
    return "Unknown error, please try again later";
  }
  if (Object.hasOwn(error.response, "detail")) {
    if (Array.isArray(error.response.detail)) {
      return error.response.detail.join("; ");
    } else {
      return String(error.response.detail);
    }
  }
};

const RemoveFsNodeModalComponent = {
  modalId: "removeFsNodeModal",
  oninit(vnode) {
    vnode.state.error = null;
  },

  sendRequest(state) {
    state.error = null;

    return m.request({
      method: "DELETE",
      url: API_V1_FSNODE,
      params: { path: FsNodeList.current.path + "/" + state.removeList[0].name },
    }).then(() => {
      closeModal(this.modalId);
      FsNodeList.elements = FsNodeList.elements.filter((item) => item != state.removeList[0]);

    }, (error) => {
      state.error = error;
    });
  },

  view(vnode) {
    return (
      m(Modal, {
        title: "Remove?",
        modalId: this.modalId,
        oninit: () => {
          vnode.state.removeList = FsNodeList.elements.filter(item => item.selected);
        },
      }, m("form.has-validation", {
        onsubmit: (e) => {
          e.preventDefault();
          this.sendRequest(vnode.state);
        },
      }, [
        m(".modal-body", [
          vnode.state.error && m(".alert alert-danger", getDetailFromError(vnode.state.error)),
          m("p", "This file will be removed"),
        ]),
        m(".modal-footer", [
          m(Button, { type: "button", class: "btn-secondary", onclick: () => {closeModal(this.modalId)} }, "Cancel"),
          m(Button, { type: "submit", class: "btn-danger" }, "Remove"),
        ]),
      ]))
    )
  }
};

export default RemoveFsNodeModalComponent;
