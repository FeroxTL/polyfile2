import m from "mithril";
import Dashboard from "./dashboard";
import { DASHBOARD_ROOT_URL } from "./urls";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, "/disk", {
	[DASHBOARD_ROOT_URL]: Dashboard,
})
