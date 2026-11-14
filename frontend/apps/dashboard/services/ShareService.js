import m from "mithril";

import { API_V1_SHARE_LIST, API_V1_SHARE_REVOKE } from "../constants/endpoints";

/**
 * Low-level service for public share operations.
 *
 * This service is backend-facing and does not keep any UI state. Callers
 * (such as DashboardFsNodeList or ShareDirectoryModal callbacks) are
 * responsible for updating their own objects after a successful request.
 */
export const ShareService = {
  /**
   * Create or update a public share for a node UUID.
   *
   * @param {string} nodeId - UUID of the node to share.
   * @param {string|null} [expiresAt] - ISO expiration timestamp, or null to clear.
   * @returns {Promise<Object>} Backend response with { id, url, status, expires_at }.
   */
  create(nodeId, expiresAt) {
    const body = { node_id: nodeId };

    if (typeof expiresAt !== "undefined") {
      body.expires_at = expiresAt;
    }

    return m.request(API_V1_SHARE_LIST, {
      method: "POST",
      body,
    });
  },

  /**
   * Revoke an active public share.
   *
   * @param {Object} share - Share object with an `id` property.
   * @returns {Promise<void>}
   */
  revoke(share) {
    const shareToken = share?.id;
    if (!shareToken) {
      return Promise.resolve();
    }

    return m.request(m.buildPathname(API_V1_SHARE_REVOKE, {
      share_token: shareToken,
    }), {
      method: "POST",
    });
  },
};
