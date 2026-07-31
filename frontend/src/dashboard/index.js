import { DASHBOARD_ROOT_URL } from "./urls";
import Dashboard from "./dashboard";
import m from "mithril";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, "/disk", {
	[DASHBOARD_ROOT_URL]: Dashboard,
})
