import m from "mithril";

export const Spinner = {
  view(vnode) {
    return (
      m(".spinner-border[role=status]", {
        style: {
          height: vnode.attrs.size,
          width: vnode.attrs.size,
        }
      }, m("span.visually-hidden", "Loading"))
    )
  }
}
