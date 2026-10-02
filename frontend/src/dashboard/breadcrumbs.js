// FsNode breadcrumbs component
import m from "mithril";
import {FsNodeList} from "./dashboard";


const FsNodeBcLink = {
  view(vnode) {
    const isLast = vnode.attrs.index === vnode.attrs.array.length - 1,
      itemName = vnode.attrs.index === 0 ? "Files" : vnode.attrs.name,
      url = encodeURIComponent(`/files${vnode.attrs.array.slice(0, vnode.attrs.index + 1).join("/")}`).replaceAll("%2F", "/");

    return m("li.breadcrumb-item", {
      class: isLast ? "active" : null,
    }, isLast ? itemName : m(m.route.Link, {href: url}, itemName))
  }
}

export const FsNodeListBreadcrumbsComponent = {
  view() {
    if (FsNodeList.current === null) {
      return null
    }

    return (
      m("nav[aria-label=breadcrumb]",
        m("ol.breadcrumb mb-0", FsNodeList.current.path.split("/").map((name, index, array) => (
          m(FsNodeBcLink, {name, index, array})
        )))
      )
    )
  }
};
