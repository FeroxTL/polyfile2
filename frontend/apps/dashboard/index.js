import { FILES_DASHBOARD_URL, DEFAULT_ROOT_URL, SHARES_DASHBOARD_URL } from "./constants/endpoints";
import { DashboardView } from "./dashboard";
import { SharesDashboardView } from "./views/SharesDashboardView";
import m from "mithril";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, DEFAULT_ROOT_URL, {
  [FILES_DASHBOARD_URL]: DashboardView,
  [SHARES_DASHBOARD_URL]: SharesDashboardView,
});
