import {FILES_DASHBOARD_URL, DEFAULT_ROOT_URL, SHARES_DASHBOARD_URL, API_V1_FSNODE} from "./constants/endpoints";
import { DashboardView } from "./dashboard";
import { SharesDashboardView } from "./views/SharesDashboardView";
import m from "mithril";
import {DashboardFsNodeList} from "./services/DashboardFsNodeList";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, DEFAULT_ROOT_URL, {
  [FILES_DASHBOARD_URL]: {
    onmatch: (args) => {
      DashboardFsNodeList.load(API_V1_FSNODE, { path: args.path });
      return DashboardView;
    }
  },
  [SHARES_DASHBOARD_URL]: SharesDashboardView,
});
