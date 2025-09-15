import m from "mithril";

const Button = {
  view(vnode) {
    return m((vnode.attrs.selector || "button") + ".btn", {
      class: vnode.attrs.class || vnode.attrs.class || "btn-primary",
      type: vnode.attrs.type || "button",
      onclick: vnode.attrs.onclick,
      disabled: vnode.attrs.disabled,
    }, vnode.children);
  }
};

export default Button;
