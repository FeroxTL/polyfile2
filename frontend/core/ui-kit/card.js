import m from "mithril";

/*
* Bootstrap Card.
* */
export default {
  view(vnode) {
    const {title} = vnode.attrs;

    return (
      m(".card", {
        class: vnode.attrs.class,
        style: vnode.attrs.style,
      }, [
        title && m(".card-header", title),
        m(".card-body", vnode.children),
      ])
    )
  }
}
