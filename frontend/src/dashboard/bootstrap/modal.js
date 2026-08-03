import m from "mithril";

const activeModals = new Set();
let fullScreenModals = 0;

function closeModal(modalId) {
  activeModals.delete(modalId);
}

function showModal(modalId) {
  activeModals.add(modalId);
}

// Backdrop wrapper
const ModalBackdrop = {
  view() {
    if (activeModals.size === 0 || fullScreenModals !== 0) {return null;}

    return (
      m(".modal-backdrop fade", {
        oncreate: (vnode) => {
          // Trigger a reflow to ensure the initial state is painted
          vnode.dom.offsetHeight;
          // Start fade in animation
          vnode.dom.classList.add("show");
        },

        onbeforeremove: (vnode) => (
          // Start fade out animation
          new Promise((resolve) => {
            vnode.dom.classList.remove("show");
            vnode.dom.addEventListener("transitionend", resolve);
          })
        ),
      })
    )
  }
};

// Main body of modal, separated for animations
const _Modal = {
  oninit(vnode) {
    if (!Object.hasOwn(vnode.attrs, "fade")) {
      vnode.attrs.fade = true;
    };
    if (vnode.attrs.fullScreen) { fullScreenModals++ };
    if (!vnode.attrs.modalId) {throw new Error("Modal.attrs.modalId is required");}
  },

  oncreate(vnode) {
    // Trigger a reflow to ensure the initial state is painted
    vnode.dom.offsetHeight;
    // Start fade in animation
    vnode.dom.classList.add("show");
  },

  onbeforeremove(vnode) {
    closeModal(vnode.attrs.modalId);
    if (!vnode.attrs.fade) {return null};

    return new Promise((resolve) => {
      // Start fade out animation
      vnode.dom.classList.remove("show");
      // Remove element from dom only after transition is finished
      vnode.dom.addEventListener("transitionend", resolve)
    })
  },

  onremove(vnode) {
    if (vnode.attrs.fullScreen) { fullScreenModals-- };
  },

  view(vnode) {
    return (
      m(".modal app-ignore-selection d-block", {
          class: vnode.attrs.fade ? "fade" : "show",
          onclick: (e) => {
            // Click on backdrop, close modal
            if (e.target.classList.contains("modal")) {
              closeModal(vnode.attrs.modalId);
            };
          }
        },
        m(".modal-dialog", {
            class: vnode.attrs.fullScreen ? "modal-fullscreen" : "",
          },
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
    if (!activeModals.has(vnode.attrs.modalId)) {return null};

    return (
      m(_Modal, vnode.attrs, vnode.children)
    )
  }
};

export { Modal, ModalBackdrop, closeModal, showModal };
