import m from "mithril";
import { NavLink } from "../bootstrap/navlink";
import Collapse from "../bootstrap/collapse";
import { uploadFile } from "../modals/uploader";
import { showModal } from "../bootstrap/modal";
import CreateDirectoryModal from "../modals/create_directory_modal";

// Navbar on the top - only for mobile (xs) devices
export const DashboardMobileNavBarView = {
  oninit(vnode) {
    vnode.state.collapsed = true;
  },

  view(vnode) {
    return (
      m("nav.navbar bg-light d-md-none", [
        m("a.navbar-brand[href=#]", "Polyfile"),
        m("button[type=button][aria-label=Toggle navigation].navbar-toggler", {
          onclick: () => { vnode.state.collapsed = !vnode.state.collapsed },
        }, m("span.navbar-toggler-icon")),
        m(Collapse, { collapsed: vnode.state.collapsed, class: "navbar-collapse" },
          m("div.mb-2", [
            m("label.btn.btn-primary.w-100.mb-2", [
              m("span", "Upload"),
              m("input.visually-hidden.w-100", {
                type: "file",
                multiple: true,
                onchange: uploadFile,
              })
            ]),
            m("button.btn.btn-outline-secondary.w-100.mb-2", {
              onclick: () => showModal(CreateDirectoryModal),
            }, "Create"),
          ]),
          m("ul.navbar-nav me-auto mb-2 mb-lg-0", [
            (vnode.attrs.items || []).map((item) => (
              m("li.nav-item", { key: item.id }, m(NavLink, {
                class: vnode.attrs.activeId === item.id ? "active" : "",
                href: item.url,
              }, item.name))
            ))
          ])
        )
      ])
    )
  }
};
