import m from "mithril";
import {normalizePath} from "@polyfile/core/utils/urls";
import {API_V1_FSNODE, API_V1_FSNODE_BY_ID} from "./constants/endpoints";
import {DashboardFsNodeList} from "./services/DashboardFsNodeList";

/**
 * Load the list data for a `/files` route.
 *
 * The route URL stays path-based, but the data is fetched by UUID whenever we
 * already know it: from a pending double-click preload or from the
 * `initial-fs-node` data embedded into the initial HTML document. The path
 * lookup is the fallback (full page reload, breadcrumb links, deep links).
 *
 * @param {string} path - Path from the route arguments.
 * @param {{path: string, node_id: string|null}|null} [initialFsNode] - Node data
 *   embedded by the server for the initial document load. Pass it only on the
 *   first match.
 * @returns {void}
 */
export const loadDashboardRoute = (path, initialFsNode = null) => {
  if (DashboardFsNodeList.consumePendingPath(path)) {
    return;
  }

  if (
    initialFsNode?.node_id
    && normalizePath(initialFsNode.path) === normalizePath(path)
  ) {
    DashboardFsNodeList.load(
      m.buildPathname(API_V1_FSNODE_BY_ID, { id: initialFsNode.node_id }),
      {},
    );
    return;
  }

  DashboardFsNodeList.load(API_V1_FSNODE, { path });
};
