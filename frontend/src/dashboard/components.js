import m from "mithril";

// Navigation link element for sidebar
const NavLink = {
  view(vnode) {
    const classList = ["nav-link"];
    if (vnode.attrs.isActive) {
      classList.push("active");
    };

    return m("a", {
      href: vnode.attrs.href || "#",
      class: classList.join(" "),
    }, vnode.children);
  }
};

export { NavLink };
