import m from "mithril";
import stream from "mithril/stream";
import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import {
  FsNodeList,
  FsNode
} from "../dashboard";
import { API_V1_FSNODE_MKDIR } from "../urls";
import Input from "../bootstrap/input";
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

const CreateDirectoryModalComponent = {
  modalId: "createDirectoryModal",
  oninit(vnode) {
    vnode.state.error = null;
    vnode.state.valueStream = stream("");
    vnode.state.fieldErrors = [];
  },

  validateValue(vnode, value) {
    vnode.state.fieldErrors.length = 0;
    const slashRegex = /^[^\/]*$/gm;
    if (!slashRegex.test(value)) {
      vnode.state.fieldErrors.push("Do no use symbol \"/\"");
    };
    if (!value) {
      vnode.state.fieldErrors.push("");
    }
  },

  sendRequest(state) {
    state.error = null;

    return m.request({
      method: "POST",
      url: API_V1_FSNODE_MKDIR,
      params: { path: FsNodeList.current.path + "/" + state.valueStream() },
    }).then((data) => {
      closeModal(this.modalId);
      const fsNode = new FsNode(data);
      FsNodeList.elements.push(fsNode);
      FsNodeList.selectFsNode(fsNode);
    }, (error) => {
      if (400 < error.code && error.code < 500) {
        state.fieldErrors.push(getDetailFromError(error));
      } else {
        state.error = error;
      };
    });
  },

  view(vnode) {
    return (
      m(Modal, {
        title: "Create directory",
        modalId: this.modalId,
      }, m("form.has-validation", {
        oninit: () => {
          vnode.state.valueStream("New directory");
          vnode.state.fieldErrors.length = 0;
        },
        onsubmit: (e) => {
          e.preventDefault();
          if (vnode.state.fieldErrors.length) return;
          this.sendRequest(vnode.state);
        },
      }, [
        m(".modal-body", [
          vnode.state.error && m(".alert alert-danger", getDetailFromError(vnode.state.error)),
          m(".mb-3",
            m(Input, {
              stream: vnode.state.valueStream,
              required: true,
              autofocus: true,
              errors: vnode.state.fieldErrors.filter(Boolean),
              oninput: () => {
                this.validateValue(vnode, vnode.state.valueStream());
              }
            }),
          ),
        ]),
        m(".modal-footer", [
          m(Button, { type: "submit", disabled: vnode.state.fieldErrors.length }, "Create"),
        ]),
      ]))
    )
  }
};

export default CreateDirectoryModalComponent;
