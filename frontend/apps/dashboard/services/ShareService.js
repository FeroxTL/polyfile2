import m from "mithril";

import { encodePath } from "@polyfile/core/utils/urls";
import { API_V1_SHARE_CREATE, API_V1_SHARE_REVOKE } from "../constants/endpoints";

/**
 * Low-level service for public share operations.
 *
 * This service is backend-facing and does not keep any UI state. Callers
 * (such as DashboardFsNodeList or ShareDirectoryModal callbacks) are
 * responsible for updating their own objects after a successful request.
 */
export const ShareService = {
  /**
   * Create or update a public share for a node path.
   *
   * @param {string} path - Full owner-relative node path.
   * @param {string|null} [expiresAt] - ISO expiration timestamp, or null to clear.
   * @returns {Promise<Object>} Backend response with { share, expires_at }.
   */
  create(path, expiresAt) {
    const body = {};

    if (typeof expiresAt !== "undefined") {
      body.expires_at = expiresAt;
    }

    return m.request(m.buildPathname(API_V1_SHARE_CREATE, {
      path: encodePath(path),
    }), {
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
