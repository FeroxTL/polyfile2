import { DashboardFsNodeList } from "../services/DashboardFsNodeList";
import {
  Modal,
  closeModal,
} from "../bootstrap/modal";
import Button from "@polyfile/core/ui-kit/button";
import { Input } from "@polyfile/core/ui-kit/input";
import { getFsNodeNameErrors } from "@polyfile/core/utils/validation";
import { getApiErrorDetail } from "./errors";
import m from "mithril";
import stream from "mithril/stream";

const RESPONSE_BAD_REQUEST = 400;
const RESPONSE_SERVER_ERROR = 500;

const validateValue = (vnode) => {
  vnode.state.fieldErrors = getFsNodeNameErrors(vnode.state.valueStream());
};

const sendRequest = (vnode) => {
  vnode.state.error = null;
  validateValue(vnode);

  if (vnode.state.fieldErrors.length) {
    return Promise.resolve();
  }

  if (vnode.state.valueStream() === vnode.state.fsNode.name) {
    return Promise.resolve();
  }

  return DashboardFsNodeList.renameFsNode(
    vnode.state.fsNode,
    vnode.state.valueStream(),
  ).then(() => {
    closeModal(vnode.attrs.modalId);
  }, (error) => {
    if (error.code >= RESPONSE_BAD_REQUEST && error.code < RESPONSE_SERVER_ERROR) {
      vnode.state.fieldErrors = [getApiErrorDetail(error)];
    } else {
      vnode.state.error = error;
    }
  });
};

const RenameFsNodeModal = {
  oninit(vnode) {
    vnode.state.fsNode = vnode.attrs.fsNode
      || DashboardFsNodeList.elements.find((item) => item.selected)
      || null;
    vnode.state.valueStream = stream(vnode.state.fsNode?.name || "");
    vnode.state.fieldErrors = [];
    vnode.state.error = null;
  },

  view(vnode) {
    const { fsNode } = vnode.state;
    const value = vnode.state.valueStream();
    const canSubmit = Boolean(fsNode)
      && value !== fsNode.name
      && getFsNodeNameErrors(value).length === 0;

    return (
      m(Modal, vnode.attrs,
        m(".modal-dialog",
          m(".modal-content", [
            m(Modal.modalHeader, { title: "Rename", ...vnode.attrs }),
            m("form.has-validation", {
              onsubmit: (e) => {
                e.preventDefault();
                if (canSubmit) {
                  sendRequest(vnode);
                }
              },
            }, [
              m(".modal-body", [
                vnode.state.error && m(".alert alert-danger", getApiErrorDetail(vnode.state.error)),
                m(".mb-3",
                  m(Input, {
                    stream: vnode.state.valueStream,
                    required: true,
                    autofocus: true,
                    selectOnFocus: true,
                    errors: vnode.state.fieldErrors.filter(Boolean),
                    oninput: () => validateValue(vnode),
                  }),
                ),
              ]),
              m(".modal-footer", [
                m(Button, {
                  type: "button",
                  class: "btn-secondary",
                  onclick: () => closeModal(vnode.attrs.modalId),
                }, "Cancel"),
                m(Button, { type: "submit", disabled: !canSubmit }, "Rename"),
              ]),
            ]),
          ]),
        ),
      )
    );
  },
};

export { RenameFsNodeModal, sendRequest as sendRenameFsNodeRequest };
