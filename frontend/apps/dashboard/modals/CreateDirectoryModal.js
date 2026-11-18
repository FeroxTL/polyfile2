import {DashboardFsNode} from "../models/DashboardFsNode";
import {DashboardFsNodeList} from "../services/DashboardFsNodeList";
import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import { API_V1_FSNODE_MKDIR } from "../constants/endpoints";
import Button from "@polyfile/core/ui-kit/button";
import {Input} from "@polyfile/core/ui-kit/input";
import { getFsNodeNameErrors } from "@polyfile/core/utils/validation";
import { getApiErrorDetail } from "./Errors";
import m from "mithril";
import stream from "mithril/stream";

const RESPONSE_BAD_REQUEST = 400;
const RESPONSE_SERVER_ERROR = 500;


const sendRequest = (vnode) => {
  vnode.state.error = null;

  return m.request({
    method: "POST",
    url: API_V1_FSNODE_MKDIR,
    body: {
      parent_id: DashboardFsNodeList.current?.id || null,
      name: vnode.state.valueStream(),
    },
  }).then((data) => {
    closeModal(vnode.attrs.modalId);
    const fsNode = new DashboardFsNode(data);
    DashboardFsNodeList.addFsNode(fsNode);
    DashboardFsNodeList.selectFsNode(fsNode);
  }, (error) => {
    if (error.code >= RESPONSE_BAD_REQUEST && error.code < RESPONSE_SERVER_ERROR) {
      vnode.state.fieldErrors.push(getApiErrorDetail(error));
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
    vnode.state.fieldErrors.push(...getFsNodeNameErrors(value));
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
                vnode.state.error && m(".alert alert-danger", getApiErrorDetail(vnode.state.error)),
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

export { CreateDirectoryModal, sendRequest as sendCreateDirectoryRequest };
