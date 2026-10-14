import {FsNodeList} from "@polyfile/core/services/FsNodeList";
import {joinPath} from "@polyfile/core/utils/urls";
import {DashboardFsNode} from "../models/DashboardFsNode";
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
  }

  /**
   * Create or reactivate a public share for a list node.
   *
   * @param {FsNode} fsNode - Node from `elements` to share.
   * @param {string} [path] - Explicit node path. Falls back to current directory + node name.
   * @param {string|null} [expiresAt] - Optional ISO expiration. `null` clears an existing expiry.
   * @returns {Promise<Object>} Backend share response.
   */
  createShare(fsNode, path, expiresAt) {
    const targetPath = path || joinPath(this.current?.path, fsNode.name);

    return ShareService.create(targetPath, expiresAt).then((data) => {
      fsNode.share = {
        ...(data.share || {}),
        expires_at: data.expires_at || null,
      };
      if (!data.share) {
        fsNode.share = null;
      }
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
