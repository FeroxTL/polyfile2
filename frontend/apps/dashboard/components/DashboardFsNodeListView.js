import m from "mithril";
import {FsNodeListView} from "@polyfile/core/components/FsNodeListView";
import {FsNodeEmptyDirectoryView} from "./FsNodeEmptyDirectoryView";

const renderShareAction = (onShareClick, fsNode) => {
  if (!fsNode.share || !onShareClick) {
    return null;
  }

  return m("button.btn btn-link p-0 ms-2 text-reset", {
    type: "button",
    title: "Open share link",
    "aria-label": "Open share link",
    onclick: (e) => {
      e.preventDefault();
      e.stopPropagation();
      onShareClick(fsNode);
    },
  }, m("i.fa fa-link[aria-hidden=true]"));
};

export class DashboardFsNodeListView extends FsNodeListView {
  EmptyListView = FsNodeEmptyDirectoryView

  childViewAttrs(vnode, item) {
    return {
      ...super.childViewAttrs(vnode, item),
      renderActions: (fsNode) => renderShareAction(vnode.attrs.onShareClick, fsNode),
    };
  }
}
