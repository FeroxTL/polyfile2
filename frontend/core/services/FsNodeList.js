// File list data
import m from "mithril";
import Sorters from "../utils/sorters";
import FsNode from "../models/FsNode";

export const XHR_READY_STATE_DONE = 4;


export class FsNodeList {
  constructor(FsNodeCls = FsNode) {
    this.FsNodeCls = FsNodeCls
    this.current = null
    this.ancestors = []
    this.elements = []
    this.error = null
    this.xhr = null
    // Public shares clip the ancestor chain at the share root; its name stays hidden.
    this.stripShareRoot = false
  }

  /**
   * Nodes of the breadcrumb chain, excluding the virtual root: the ancestor
   * chain (clipped at the share root for public shares) and the current node.
   */
  get breadcrumbNodes() {
    if (this.current === null) {
      return [];
    }

    const nodes = this.ancestors.slice(this.stripShareRoot ? 1 : 0);
    // The share root has its parent_id masked and must render as "/".
    if (this.current.parent_id || !this.stripShareRoot) {
      nodes.push(this.current);
    }
    return nodes.filter((node) => node.name);
  }

  /**
   * Names of the directories leading to the current node, including its own.
   *
   * The backend no longer ships `path` in list responses; the ancestor chain
   * (ancestors + current name) fully determines it.
   */
  get pathSegments() {
    return this.breadcrumbNodes.map((node) => node.name);
  }

  /**
   * Display path of the current node, e.g. "/root/sub".
   */
  get path() {
    return `/${this.pathSegments.join("/")}`;
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
      this.ancestors = data.ancestors || [];

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
