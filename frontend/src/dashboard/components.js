import m from "mithril";

// Navigation link element for sidebar
const NavLink = {
  view(vnode) {
    return m("a.nav-link", {
      href: vnode.attrs.href || "#",
      class: vnode.attrs.class,
    }, vnode.children);
  }
};

export { NavLink };
