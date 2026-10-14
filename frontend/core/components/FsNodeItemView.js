import m from "mithril";
import {showModal} from "../../apps/dashboard/bootstrap/modal";
import ImageViewerModal from "../../apps/dashboard/image_viewer";
import {validateAttributes} from "@polyfile/core/utils/validation";

const FsNodeItemView = {
  oncreate(vnode) {
    validateAttributes(vnode.attrs, ["fsnodeList", "fsNode"]);
  },

  navigate(fsNode, event, fsnodeList, navigationHandler) {
    if (fsNode.type === "file") {
      showModal(ImageViewerModal, { 
        currentImg: fsNode, 
        items: fsnodeList.elements.filter(item => item.type === "file") 
      });
    } else if (navigationHandler) {
      navigationHandler(fsnodeList.current.path, fsNode.name);
    }
    event.preventDefault();
    return false;
  },

  view(vnode) {
    const { navigationHandler, fsnodeList, fsNode, renderActions } = vnode.attrs;

    return (
      m("li[role=button].list-group-item list-group-item-action list-group-item-light py-3 d-flex justify-content-between", {
          class: fsNode.selected ? "active" : null,
          'aria-current': fsNode.selected ? String(fsNode.selected) : null,
          onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            fsnodeList.selectFsNode(fsNode);
          },
          ondblclick: (e) => this.navigate(fsNode, e, fsnodeList, navigationHandler),
        }, [
          m("span.fsnode-icon", m("i.h4 mb-0 fa", { class: fsNode.type === "directory" ? "fa-folder" : "fa-file" })),
          m("span.flex-grow-1 ms-2", fsNode.name),
          m(".d-flex.align-items-center", [
            m("span.d-none d-sm-block", fsNode.type),
            renderActions && renderActions(fsNode),
          ]),
        ]
      )
    )
  }
};

export default FsNodeItemView;
