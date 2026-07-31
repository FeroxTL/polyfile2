import CreateDirectoryModalComponent from "./modals/create_directory_modal";
import { NavLink } from "./components";
import m from "mithril";
import { showModal } from "./bootstrap/modal";
import { uploadFile } from "./modals/uploader";


// Sidebar on left side of dashboard - only for md width
const DashboardSideBar = {
  view(vnode) {
    return (
      m(".app-sidebar vh-100 overflow-y-auto p-3 d-md-flex d-none flex-column border-end bg-light", [
        // Title
        m("a[href=/].d-flex align-items-center mb-3 mb-md-0 text-dark me-md-auto text-decoration-none",
          m("span.fs-4", "Polyfile"),
        ),

        m("hr"),

        // Navigation Links
        m("ul.nav nav-pills flex-column mb-auto", (vnode.attrs.items || []).map((item) => (
          m("li.nav-item", { key: item.id }, m(NavLink, { href: item.url, isActive: vnode.attrs.activeId === item.id }, item.name))
        ))),

        // Upload and Create Buttons
        m(".mt-auto pt-3 border-top", [
          m("label.btn btn-primary w-100 mb-2", [
            m("span.fa fa-upload[aria-hidden=true]"), " ", "Upload",
            m("input.d-none[type=file]", { onchange: uploadFile }),
          ]),
          m("button.btn btn-outline-secondary w-100", {
            onclick: () => showModal(CreateDirectoryModalComponent.modalId),
          }, [m("span.fa fa-folder-plus[aria-hidden=true]"), " ", "Create"]),
        ]),
      ])
    );
  }
};

export default DashboardSideBar;
