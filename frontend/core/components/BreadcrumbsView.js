import m from "mithril";
import {ensureAttribute} from "../utils/validation"
import {joinPath} from "../utils/urls";

const FsNodeBcLink = {
  view(vnode) {
    const
      {name, index, array, getPublicUrl, onNavigate, node} = vnode.attrs,
      isLast = vnode.attrs.index === array.length - 1;
    const path = joinPath(...array.slice(0, index + 1));
    const linkAttrs = { href: getPublicUrl(path) };

    if (node?.id && onNavigate) {
      /* Preload the target by UUID; m.route.Link still performs the
      path-based navigation and keeps modifier clicks working. */
      linkAttrs.onclick = () => onNavigate(node, path);
    }

    return m("li.breadcrumb-item", {
      class: isLast ? "active" : null,
    }, isLast ? name : m(m.route.Link, linkAttrs, name))
  }
}

export class BreadcrumbsView {
  constructor(vnode) {
    this.FsNodeList = ensureAttribute(vnode.attrs.FsNodeList);
    this.getPublicUrl = ensureAttribute(vnode.attrs.getPublicUrl);
  }

  view(vnode) {
    if (this.FsNodeList.current === null) {
      return null
    }

    const pathArray = ["", ...this.FsNodeList.pathSegments];
    const nodes = this.FsNodeList.breadcrumbNodes || [];

    return (
      m("div.card",
        m("nav.card-body[aria-label=breadcrumb].d-flex.align-items-center.gap-2",
          [
            m("ol.breadcrumb mb-0 flex-grow-1", pathArray.map((name, index, array) => (
              m(FsNodeBcLink, {
                name: index === 0 ? "Files" : name,
                index,
                array,
                getPublicUrl: this.getPublicUrl,
                onNavigate: vnode.attrs.onNavigate,
                node: nodes[index - 1],
              })
            ))),
            vnode.attrs.actions,
          ]
        )
      )
    )
  }
}
