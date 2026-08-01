import m from "mithril";

const Card = {
  view(vnode) {
    return (
      m(".card", {
        class: vnode.attrs.class,
      }, [
        m(".card-header", "Error"),
        m(".card-body", vnode.children),
      ])
    )
  }
}

export default Card;
