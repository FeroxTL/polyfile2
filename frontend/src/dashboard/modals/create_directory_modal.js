import {
  FsNode,
  FsNodeList
} from "../dashboard";
import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import { API_V1_FSNODE_MKDIR } from "../urls";
import Button from "../bootstrap/button";
import Input from "../bootstrap/input";
import m from "mithril";
import stream from "mithril/stream";

const ERROR_CODE_ZERO = 0;
const RESPONSE_BAD_REQUEST = 400;
const RESPONSE_SERVER_ERROR = 500;

const getDetailFromError = (error) => {
  if (error.code === ERROR_CODE_ZERO || error.response === null) {
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

  return m.request({
    method: "POST",
    url: API_V1_FSNODE_MKDIR,
    params: { path: `${FsNodeList.current.path  }/${  vnode.state.valueStream()}` },
  }).then((data) => {
    closeModal(vnode.attrs.modalId);
    const fsNode = new FsNode(data);
    FsNodeList.addFsNode(fsNode);
    FsNodeList.selectFsNode(fsNode);
  }, (error) => {
    if (error.code >= RESPONSE_BAD_REQUEST && error.code < RESPONSE_SERVER_ERROR) {
      vnode.state.fieldErrors.push(getDetailFromError(error));
    } else {
      vnode.state.error = error;
    }
  });
};


const CreateDirectoryModal = {
  oninit(vnode) {
    vnode.state.error = null;
    vnode.state.valueStream = stream("");
    vnode.state.fieldErrors = [];
  },

  validateValue(vnode, value) {
    vnode.state.fieldErrors.length = 0;
    const slashRegex = /^[^/]*$/ugm;
    if (!slashRegex.test(value)) {
      vnode.state.fieldErrors.push("Do no use symbol \"/\"");
    }
    if (!value) {
      vnode.state.fieldErrors.push("");
    }
  },

  view(vnode) {
    return (
      m(Modal, vnode.attrs,
        m(".modal-dialog",
          m(".modal-content", [
            m(Modal.modalHeader, {title: "Create directory", ...vnode.attrs}),
            m("form.has-validation", {
              oninit: () => {
                vnode.state.valueStream("New directory");
                vnode.state.fieldErrors.length = 0;
              },
              onsubmit: (e) => {
                e.preventDefault();
                if (vnode.state.fieldErrors.length) {return}
                sendRequest(vnode);
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
            ])
          ])
        ),
      )
    )
  }
};

export default CreateDirectoryModal;
