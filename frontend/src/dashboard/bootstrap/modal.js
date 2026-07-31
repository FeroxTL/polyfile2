import m from "mithril";

const activeModals = new Set();

function closeModal(modalId) {
  activeModals.delete(modalId);
}

function showModal(modalId) {
  activeModals.add(modalId);
}

const _ModalBackdrop = {
  oninit(vnode) {
    vnode.state.show = false;
  },

  oncreate(vnode) {
    // Start fade in animation
    return new Promise(resolve => {
      vnode.state.show = true;
      m.redraw();
      resolve();
    });
  },

  onbeforeremove(vnode) {
    // Start fade out animation
    vnode.dom.classList.remove("show");
    vnode.state.show = false;

    return new Promise((resolve) => {
      vnode.dom.addEventListener("transitionend", resolve)
    })
  },

  onremove() {
    // Modal body was removed
    m.redraw();
  },

  view(vnode) {
    return (
      m(".modal-backdrop fade", { class: vnode.state.show ? "show" : ""})
    )
  }
};

// Backdrop wrapper
const ModalBackdrop = {
  view() {
    if (activeModals.size === 0) {return null;}

    return (
      m(_ModalBackdrop)
    )
  }
};

// Main body of modal, separated for animations
const _Modal = {
  oninit(vnode) {
    if (!vnode.attrs.modalId) {throw new Error("Modal.attrs.modalId is required");}
    // If modal is actually shown with all animations
    vnode.state.show = false;
  },

  oncreate(vnode) {
    // Start fade in animation
    vnode.dom.classList.add("d-block");
    vnode.state.show = true;
  },

  onbeforeremove(vnode) {
    // Start fade out animation
    vnode.dom.classList.remove("show");
    closeModal(vnode.attrs.modalId);

    return new Promise((resolve) => {
      // Remove element from dom only after transition is finished
      vnode.dom.addEventListener("transitionend", resolve)
    })
  },

  onremove(vnode) {
    // Hiding modal animation
    vnode.state.show = false;
    m.redraw();
  },

  view(vnode) {
    return (
      m(".modal fade app-ignore-selection", {
          class: vnode.state.show ? "show d-block" : "",
          onclick: (e) => {
            // Click on backdrop, close modal
            if (e.target.classList.contains("modal")) {
              closeModal(vnode.attrs.modalId);
            };
          }
        },
        m(".modal-dialog",
          m(".modal-content", [
            m(".modal-header", [
              m("h5", vnode.attrs.title),
              m("button.btn-close[aria-label=Close]", { onclick: () => {closeModal(vnode.attrs.modalId); return false;} }),
            ]),
            vnode.children,
          ])
        )
      )
    )
  }
};

// Modal wrapper
const Modal = {
  view(vnode) {
    if (!activeModals.has(vnode.attrs.modalId)) {return null;}

    return (
      m(_Modal, vnode.attrs, vnode.children)
    )
  }
};

export { Modal, ModalBackdrop, closeModal, showModal };
