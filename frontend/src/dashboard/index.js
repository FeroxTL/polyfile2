import { FILES_DASHBOARD_URL, DEFAULT_ROOT_URL } from "./urls";
import Dashboard from "./dashboard";
import m from "mithril";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, DEFAULT_ROOT_URL, {
	[FILES_DASHBOARD_URL]: Dashboard,
})
