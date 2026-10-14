import m from "mithril";
import FsNodeItemView from "./FsNodeItemView";
import {FsNodeErrorView} from "./FsNodeErrorView";
import {validateAttributes} from "@polyfile/core/utils/validation";

/**
 * Mithril component displayed when a directory contains no child nodes.
 */
export const FsNodeListEmptyView = {
  view() {
    return m("span", "This directory is empty")
  }
}


/**
 * Mithril component that displays a list of filesystem nodes.
 * 
 * This component handles the rendering of file and directory structures, providing a list view that supports:
 * - Breadcrumbs and Action Bars (optional)
 * - Loading and Error states
 * - Empty state display
 * - Selection via document click events
 *
 * @param {Object} vnode - The Mithril virtual node.
 * @param {Object} vnode.attrs - Attributes for the component.
 * @param {Object} vnode.attrs.fsnodeList - The object representing the filesystem node list,
 *                                            containing elements, loading state, and error information.
 * @param {Function} [vnode.attrs.navigationHandler] - A handler for navigation events.
 * @param {Function} [vnode.attrs.breadcrumbs] - A component to render breadcrumbs.
 * @param {Function} [vnode.attrs.actionBar] - A component to render an action bar.
 */
export class FsNodeListView {
  FsNodeChildView = FsNodeItemView
  EmptyListView = FsNodeListEmptyView

  constructor(vnode) {
    validateAttributes(
      vnode.attrs,
      ["fsnodeList", "navigationHandler"],
    );
    this.fsnodeList = vnode.attrs.fsnodeList;
    this.onDocumentClick = this.onDocumentClick.bind(this);
  }

  onDocumentClick(e) {
    if ((!e.target.closest(".app-ignore-selection")) && this.fsnodeList) {
      this.fsnodeList.selectFsNode();
      m.redraw();
    }
  }

  oncreate() {
    document.addEventListener("click", this.onDocumentClick);
  }

  onremove() {
    document.removeEventListener("click", this.onDocumentClick);
  }

  childViewAttrs(vnode, item) {
    return {
      fsNode: item,
      fsnodeList: this.fsnodeList,
      navigationHandler: vnode.attrs.navigationHandler,
    };
  }

  view(vnode) {
    const { onRetry } = vnode.attrs;
    // Check if we are currently loading
    if (this.fsnodeList.is_loading) {
      return m("div.flex-grow-1 vh-100", [
        m("p.text-center mt-5", "Loading..")
      ]);
    }

    if (this.fsnodeList.has_error) {
      return m(FsNodeErrorView, {
        error: this.fsnodeList.error,
        onRetry,
      });
    }

    return m("div.flex-grow-1 my-md-2 my-1", [
      // Empty State
      this.fsnodeList.elements.length === 0 && m(this.EmptyListView),

      // List Mapping
      m("ul.list-group user-select-none", this.fsnodeList.elements.map((item) => (
        m(this.FsNodeChildView, this.childViewAttrs(vnode, item))
      )))
    ]);
  }
}
