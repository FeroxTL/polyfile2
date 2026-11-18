import m from "mithril";
import {FsNodeList} from "@polyfile/core/services/FsNodeList";
import {normalizePath} from "@polyfile/core/utils/urls";
import {DashboardFsNode} from "../models/DashboardFsNode";
import {API_V1_FSNODE_BY_ID} from "../constants/endpoints";
import {ShareService} from "./ShareService";

/**
 * Dashboard file list service.
 *
 * Owns the currently listed nodes and exposes dashboard-specific actions,
 * such as creating a public share and updating the target node in place.
 */
export class DashboardFsNodeListService extends FsNodeList {
  constructor() {
    super(DashboardFsNode);
    // Path the route is expected to show after a UUID preload.
    this.pendingPath = null;
  }

  /**
   * Load a node by UUID, optionally marking the route path it belongs to.
   *
   * When `expectedPath` is known (double-click, breadcrumbs), the marker lets
   * the route handler skip the duplicate path-based lookup.
   *
   * @param {string} nodeId - UUID of the directory to open.
   * @param {string|null} [expectedPath] - Path the route is about to show.
   * @returns {Promise<void>}
   */
  loadByNodeId(nodeId, expectedPath = null) {
    this.pendingPath = expectedPath === null ? null : normalizePath(expectedPath);
    return this.load(m.buildPathname(API_V1_FSNODE_BY_ID, { id: nodeId }), {});
  }

  /**
   * Mark an already loaded path so the next route match reuses the data.
   *
   * @param {string} path - Path the route is about to show.
   * @returns {void}
   */
  markPathPending(path) {
    this.pendingPath = normalizePath(path);
  }

  /**
   * Consume the UUID preload marker when it matches the route path.
   *
   * @param {string} path - Path from the route arguments.
   * @returns {boolean} True when the list is already loading that path.
   */
  consumePendingPath(path) {
    const isPending = this.pendingPath !== null
      && this.pendingPath === normalizePath(path);
    this.pendingPath = null;
    return isPending;
  }

  /**
   * Rename a node by UUID and update it in place.
   *
   * Only the leaf name changes; selection, share state and other fields of
   * the in-memory node are preserved. The list is re-sorted because the
   * name is part of the default sort order.
   *
   * @param {FsNode} fsNode - Node from `elements` to rename.
   * @param {string} name - New leaf name.
   * @returns {Promise<Object>} Backend node payload.
   */
  renameFsNode(fsNode, name) {
    return m.request(m.buildPathname(API_V1_FSNODE_BY_ID, { id: fsNode.id }), {
      method: "PATCH",
      body: { name },
    }).then((data) => {
      fsNode.name = data.name;
      fsNode.modified_at = data.modified_at;
      this.sortElements();
      return data;
    });
  }

  /**
   * Move a node under another directory by UUID.
   *
   * The node leaves the currently listed directory, so it is removed from
   * `elements` and deselected on success. A no-op move (the destination is
   * already the parent) keeps the node in place; failed requests leave the
   * in-memory list untouched.
   *
   * @param {FsNode} fsNode - Node from `elements` to move.
   * @param {string|null} parentId - Destination directory UUID; `null` means root.
   * @returns {Promise<Object>} Backend node payload.
   */
  moveFsNode(fsNode, parentId) {
    return m.request(m.buildPathname(API_V1_FSNODE_BY_ID, { id: fsNode.id }), {
      method: "PATCH",
      body: { parent_id: parentId },
    }).then((data) => {
      const wasListed = this.elements.includes(fsNode);
      const parentChanged = fsNode.parent_id !== data.parent_id;
      fsNode.parent_id = data.parent_id;

      if (wasListed && parentChanged) {
        this.elements = this.elements.filter((item) => item !== fsNode);
        fsNode.selected = false;
      }
      return data;
    });
  }

  /**
   * Create or reactivate a public share for a node by its UUID.
   *
   * @param {FsNode} fsNode - Node from `elements` to share.
   * @param {string|null} [expiresAt] - Optional ISO expiration. `null` clears an existing expiry.
   * @returns {Promise<Object>} Backend share response.
   */
  // The request only needs the node, not service state.
  // eslint-disable-next-line class-methods-use-this
  createShare(fsNode, expiresAt) {
    return ShareService.create(fsNode.id, expiresAt).then((data) => {
      fsNode.share = data?.url
        ? { id: data.id, url: data.url, expires_at: data.expires_at || null }
        : null;
      return data;
    });
  }

  /**
   * Revoke a public share for a list node.
   *
   * The backend keeps the share row for history but marks it as revoked.
   * The node's public link is removed from the in-memory list on success.
   *
   * @param {FsNode} fsNode - Node whose active share should be revoked.
   * @returns {Promise<void>}
   */
  // The request only needs the node, not service state.
  // eslint-disable-next-line class-methods-use-this
  revokeShare(fsNode) {
    return ShareService.revoke(fsNode.share).then(() => {
      fsNode.share = null;
    });
  }
}

export const DashboardFsNodeList = new DashboardFsNodeListService();
