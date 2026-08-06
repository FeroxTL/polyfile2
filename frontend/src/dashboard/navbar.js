import { NavLink } from "./bootstrap/navlink";
import m from "mithril";
import Collapse from "./bootstrap/collapse";

// Navbar on the top - only for mobile (xs) devices
const DashboardNavBar = {
  oninit(vnode) {
    vnode.state.collapsed = true;
  },

  view(vnode) {
    return (
      m("nav.navbar bg-light d-md-none", [
        m("a.navbar-brand[href=#]", "Polyfile"),
        m("button[type=button][aria-label=Toggle navigation].navbar-toggler", {
          onclick: () => { vnode.state.collapsed = !vnode.state.collapsed },
        }, m("span.navbar-toggler-icon")),
        m(Collapse, { collapsed: vnode.state.collapsed, class: "navbar-collapse" },
          m("ul.navbar-nav me-auto mb-2 mb-lg-0", [
            (vnode.attrs.items || []).map((item) => (
              m("li.nav-item", { key: item.id }, m(NavLink, {
                class: vnode.attrs.activeId === item.id ? "active" : "",
                href: item.url,
              }, item.name))
            ))
          ])
        )
      ])
    )
  }
};

export default DashboardNavBar;
