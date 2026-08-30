import m from "mithril";
import {checkAnimationsDisabled, reflow} from "../../util";

// List of all modals
const modals = new Set();
let backdropCounter = 0;

// Show component as modal
function showModal(component, options = {}) {
  const modalArgs = [component, options];
  options.modalId = modalArgs;
  options.modalShow = true;
  options.modalBackdrop = component?.backdrop ?? true;
  if (options.modalBackdrop) {
    backdropCounter++;
  }
  modals.add(modalArgs);
  return modalArgs;
}

// Close modal with specified modalId
function closeModal(modalId) {
  // Removes modal from visible and starts fade out / close animation
  const [, options] = modalId;
  if (checkAnimationsDisabled()) {
    modals.delete(modalId);
  } else {
    options.modalShow = false;
  }
  if (options.modalBackdrop) {
    backdropCounter--;
  }
}


// Modal and its backdrop
const ModalsAndBackdrop = {
  view() {
    return [
      // Render modals
      Array.from(modals).map(([component, options]) => m(component, options)),

      // Render backdrop
      backdropCounter > 0 && m(".modal-backdrop fade", {
        oncreate: (vnode) => {
          // Trigger a reflow to ensure the initial state is painted
          reflow(vnode.dom);
          // Start fade in animation
          vnode.dom.classList.add("show");
        },

        onbeforeremove: (vnode) => (
          // If animations are disabled hide immediately
          !checkAnimationsDisabled() &&
            // Start fade out animation
            new Promise((resolve) => {
              vnode.dom.classList.remove("show");
              vnode.dom.addEventListener("transitionend", resolve);
            })
        ),
      })
    ]
  }
};


const Modal = {
  modalCloseButton: {
    view(vnode) {
      return (
        m("button.btn-close[aria-label=Close]", {
          onclick: (e) => { e.preventDefault(); closeModal(vnode.attrs.modalId)},
        })
      )
    }
  },

  modalHeader: {
    view(vnode) {
      return (
        m(".modal-header", [
          m("h5", vnode.attrs.title),
          m(Modal.modalCloseButton, vnode.attrs),
        ])
      )
    },
  },

  view(vnode) {
    return vnode.attrs.modalShow && m(
      ".modal app-ignore-selection d-block", {
        class: vnode.attrs.fade === false ? "show" : "fade",
        onclick: (e) => {
          if (!e.target.closest('.modal-dialog')) {
            // Click on backdrop, close modal
            closeModal(vnode.attrs.modalId);
          }
        },
        oncreate: (v) => {
          // Trigger a reflow to ensure the initial state is painted
          reflow(v.dom);
          // Start fade in animation
          v.dom.classList.add("show");
        },
        onbeforeremove: (v) => {
          // If fading is disabled by settings or animations disabled by user
          if (!vnode.dom.classList.contains("fade") || checkAnimationsDisabled()) {return null}

          return new Promise((resolve) => {
            // Start fade out animation
            v.dom.classList.remove("show");
            // Remove element from dom only after transition is finished
            v.dom.addEventListener("transitionend", () => {
              resolve();
              // Remove modal from list
              modals.delete(vnode.attrs.modalId);
              m.redraw();
            });
          })
        },
        onremove() {
          // Modal can be already removed by "transitionend" event.
          if (modals.delete(vnode.attrs.modalId)) {
            m.redraw();
          }
        },
      },
      vnode.children,
    );
  }
};

export { Modal, ModalsAndBackdrop, showModal, closeModal };
