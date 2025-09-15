import m from "mithril";
import { NavLink } from "./components";

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
        m(Collapse, { collapsed: vnode.state.collapsed },
          m("ul.navbar-nav me-auto mb-2 mb-lg-0", [
            (vnode.attrs.items || []).map((item) => (
              m("li.nav-item", { key: item.id }, m(NavLink, {
                isActive: vnode.attrs.activeId == item.id,
                href: item.url,
              }, item.name))
            ))
          ])
        )
      ])
    )
  }
};

// Collapse elements
// 1. Add class "collapsing". Add class "show" if not collapsing attr
// 2. Start transition (height)
// 3. Wait for transition ends
// 4. Remove class "collapsing". Add class "show" or "collapse" depending on "collapse" attr
const Collapse = {
  oninit(vnode) {
    vnode.state.collapsed = vnode.attrs.collapsed || false;
  },

  oncreate(vnode) {
    vnode.dom.ontransitionend = (e) => {
      if (!vnode.dom.classList.contains("collapsing") || e.propertyName != "height") return;

      vnode.dom.classList.remove("collapsing", "collapse");
      vnode.dom.style.height = ""; // Clear explicit height for responsiveness

      if (!vnode.attrs.collapsed) {
        vnode.dom.classList.add("show");
      } else {
        vnode.dom.classList.add("collapse");
      }
    };
  },

  onupdate(vnode) {
    if (vnode.state.collapsed != vnode.attrs.collapsed) {
      // Needs state change
      vnode.state.collapsed = vnode.attrs.collapsed;
      const el = vnode.dom;

      if (!vnode.state.collapsed) {
        el.classList.add("collapsing", "show");

        el.offsetHeight;
        el.style.height = el.scrollHeight + "px";
      } else {
        el.style.height = el.getBoundingClientRect().height + "px";
        el.classList.remove("collapse", "show");
        el.classList.add("collapsing");
        el.offsetHeight;
        el.style.height = "0px";
      }
    }
  },

  view(vnode) {
    return (
      m(".collapse navbar-collapse", vnode.children)
    );
  }
};


export default DashboardNavBar;
