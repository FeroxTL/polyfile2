import m from "mithril";

/*
* Bootstrap Button.
* */
export default {
  view(vnode) {
    return m(`${vnode.attrs.selector || "button"  }.btn`, {
      title: vnode.attrs.title,
      class: vnode.attrs.class || "btn-primary",
      type: vnode.attrs.type || "button",
      onclick: vnode.attrs.onclick,
      disabled: vnode.attrs.disabled,
    }, vnode.children);
  }
};
