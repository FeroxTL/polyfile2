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
