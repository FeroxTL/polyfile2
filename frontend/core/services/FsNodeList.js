// File list data
import m from "mithril";
import Sorters from "../utils/sorters";
import FsNode from "../models/FsNode";

export const XHR_READY_STATE_DONE = 4;


export class FsNodeList {
  constructor(FsNodeCls = FsNode) {
    this.FsNodeCls = FsNodeCls
    this.current = null
    this.elements = []
    this.error = null
    this.xhr = null
  }

  get is_loading() {
    return this.xhr !== null && this.xhr.readyState !== XHR_READY_STATE_DONE;
  }

  get has_error() {
    return this.error !== null;
  }

  load(url, params) {
    if (this.xhr !== null) {this.xhr.abort();}

    return m.request(url, {
      method: "GET",
      params,
      config: (xhr) => {this.xhr = xhr},
    })
    .then((data) => {
      this.error = null;
      this.current = new this.FsNodeCls(data.current);

      const sorter = Sorters[this.current.sorting || "default"];
      this.elements = data.children.map((child) => new this.FsNodeCls(child)).sort(sorter);
    })
    .catch(error => {
      this.error = error;
    }).finally(() => {
      this.xhr = null;
    });
  }

  selectFsNode(fsNode) {
    // Select fs_node and remove selection from others
    this.elements.forEach((item) => {
      item.selected = (item === fsNode)
    });
  }

  /**
   * Add FsNode respecting sorting
   */
  addFsNode(fsNode) {
    const sorter = Sorters[this.current.sorting || "default"];
    for (let i = 0; i < this.elements.length; i++) {
      if (sorter(this.elements[i], fsNode) > 0) {
        return this.elements.splice(i, 0, fsNode);
      }
    }
    this.elements.push(fsNode);
    return this.elements;
  }
}
