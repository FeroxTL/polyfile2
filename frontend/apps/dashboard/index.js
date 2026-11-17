import {FILES_DASHBOARD_URL, DEFAULT_ROOT_URL, SHARES_DASHBOARD_URL, TRASH_DASHBOARD_URL} from "./constants/endpoints";
import { DashboardView } from "./dashboard";
import { loadDashboardRoute } from "./route";
import { SharesDashboardView } from "./views/SharesDashboardView";
import { TrashDashboardView } from "./views/TrashDashboardView";
import m from "mithril";

/**
 * Read the initial FsNode embedded by the server for this document load.
 *
 * @returns {{path: string, node_id: string|null}|null} Node data or null.
 */
const readInitialFsNode = () => {
  const element = document.getElementById("initial-fs-node");
  if (!element) {
    return null;
  }
  try {
    return JSON.parse(element.textContent);
  } catch {
    return null;
  }
};

// The server renders the initial node once; use it only for the first match.
let initialFsNode = readInitialFsNode();

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, DEFAULT_ROOT_URL, {
  [FILES_DASHBOARD_URL]: {
    onmatch: (args) => {
      loadDashboardRoute(args.path, initialFsNode);
      initialFsNode = null;
      return DashboardView;
    }
  },
  [SHARES_DASHBOARD_URL]: SharesDashboardView,
  [TRASH_DASHBOARD_URL]: TrashDashboardView,
});
