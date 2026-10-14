import m from "mithril";

const INTERNAL_URLS = ["/files/", "/shares"]

// Navigation link element for sidebar
const NavLink = {
  view(vnode) {
    const { attrs, children } = vnode;
    const classes = ["nav-link"]
    if (attrs.class) {
      classes.push(attrs.class);
    }

    return m(INTERNAL_URLS.indexOf(attrs.href) === -1 ? "a" : m.route.Link, {
      href: attrs.href || "#",
      class: classes.join(" "),
    }, children);
  }
};

export { NavLink };
