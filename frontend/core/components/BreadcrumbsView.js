import m from "mithril";
import {ensureAttribute} from "../utils/validation"
import {joinPath} from "../utils/urls";

const FsNodeBcLink = {
  view(vnode) {
    const
      {name, index, array, getPublicUrl} = vnode.attrs,
      isLast = vnode.attrs.index === array.length - 1;

    return m("li.breadcrumb-item", {
      class: isLast ? "active" : null,
    }, isLast ? name : m(m.route.Link, {
      href: getPublicUrl(joinPath(...array.slice(0, index + 1))),
    }, name))
  }
}

export class BreadcrumbsView {
  constructor(vnode) {
    this.FsNodeList = ensureAttribute(vnode.attrs.FsNodeList);
    this.getPublicUrl = ensureAttribute(vnode.attrs.getPublicUrl);
  }

  view() {
    if (this.FsNodeList.current === null) {
      return null
    }

    const pathArray = ["", ...this.FsNodeList.current.path.split('/').filter(Boolean)];

    return (
      m("div.card",
        m("nav.card-body[aria-label=breadcrumb]",
          m("ol.breadcrumb mb-0", pathArray.map((name, index, array) => (
            m(FsNodeBcLink, {
              name: index === 0 ? "Files" : name,
              index,
              array,
              getPublicUrl: this.getPublicUrl,
            })
          )))
        )
      )
    )
  }
}
