import m from "mithril";import { NavLink } from "../bootstrap/navlink";
import Collapse from "../bootstrap/collapse";
import { uploadFile } from "../modals/Uploader";
import { showModal } from "../bootstrap/modal";
import { CreateDirectoryModal } from "../modals/CreateDirectoryModal";
import { UploadMonitorModal } from "../modals/UploadMonitor";
import { UploadManager } from "../services/UploadManager";

// Navbar on the top - only for mobile (xs) devices
export const DashboardMobileNavBarView = {
  oninit(vnode) {
    vnode.state.collapsed = true;
  },

  view(vnode) {
    const { state, attrs } = vnode;

    return (
      m("nav.navbar bg-light d-md-none", [
        m("a.navbar-brand[href=#]", "Polyfile"),
        m(".d-flex.align-items-center.ms-auto", [
          m("button.btn.btn-outline-primary.me-2[type=button][aria-label=Uploads]", {
            onclick: () => showModal(UploadMonitorModal),
          }, [
            m("span.fa.fa-upload[aria-hidden=true]"),
            UploadManager.activeCount > 0
              && m("span.badge.text-bg-primary.ms-1", UploadManager.activeCount),
          ]),
          m("button[type=button][aria-label=Toggle navigation].navbar-toggler", {
            onclick: () => { state.collapsed = !state.collapsed },
          }, m("span.navbar-toggler-icon")),
        ]),
        m(Collapse, { collapsed: state.collapsed, class: "navbar-collapse" },
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
            (attrs.items || []).map((item) => (
              m("li.nav-item", { key: item.id }, m(NavLink, {
                class: attrs.activeId === item.id ? "active" : "",
                href: item.url,
              }, item.name))
            ))
          ])
        )
      ])
    )
  }
};
