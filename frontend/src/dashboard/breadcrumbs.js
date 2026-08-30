// FsNode breadcrumbs component
import m from "mithril";
import {FsNodeList} from "./dashboard";

export const FsNodeListBreadcrumbsComponent = {
  view() {
    if (FsNodeList.current === null) {
      return null
    }

    return (
      m("nav[aria-label=breadcrumb]",
        m("ol.breadcrumb mb-0", FsNodeList.current.path.split("/").map((item, index, array) => {
          const isLast = index === array.length - 1,
            itemName = index === 0 ? "Files" : item,
            url = encodeURIComponent(`/disk${array.slice(0, index + 1).join("/")}`).replaceAll("%2F", "/");
          return m("li.breadcrumb-item", {
            class: isLast ? "active" : null,
          }, isLast ? itemName : m(m.route.Link, {href: url}, itemName))
        }))
      )
    )
  }
};
