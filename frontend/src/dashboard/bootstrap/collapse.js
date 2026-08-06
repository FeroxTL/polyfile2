import m from "mithril";

// Collapse elements
// 1. Add class "collapsing". Add class "show" if not collapsing attr
// 2. Start transition (height)
// 3. Wait for transition ends
// 4. Remove class "collapsing". Add class "show" or "collapse" depending on "collapse" attr
const Collapse = {
  oninit(vnode) {
    vnode.state.collapsed = vnode.attrs.collapsed || false;
  },

  oncreate(vnode) {
    vnode.dom.ontransitionend = (e) => {
      if (!vnode.dom.classList.contains("collapsing") || e.propertyName !== "height") {return;}

      vnode.dom.classList.remove("collapsing", "collapse");
      // Clear explicit height for responsiveness
      vnode.dom.style.height = "";
      vnode.dom.classList.add(vnode.attrs.collapsed ? "collapse" : "show");
    };
  },

  onupdate(vnode) {
    if (vnode.state.collapsed !== vnode.attrs.collapsed) {
      // Needs state change
      vnode.state.collapsed = vnode.attrs.collapsed;
      const el = vnode.dom;

      if (vnode.state.collapsed) {
        el.style.height = `${el.getBoundingClientRect().height}px`;
        el.classList.remove("collapse", "show");
        el.classList.add("collapsing");
        el.offsetHeight;
        el.style.height = "0px";
      } else {
        el.classList.add("collapsing", "show");

        el.offsetHeight;
        el.style.height = `${el.scrollHeight}px`;
      }
    }
  },

  view(vnode) {
    return (
      m("div.collapse", {
        id: vnode.attrs.id,
        class: vnode.attrs.class,
      }, vnode.children)
    );
  }
};

export default Collapse;