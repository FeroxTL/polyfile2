import CreateDirectoryModalComponent from "./modals/create_directory_modal";
import { NavLink } from "./bootstrap/navlink";
import Collapse from "./bootstrap/collapse";
import m from "mithril";
import { showModal } from "./bootstrap/modal";
import { uploadFile } from "./modals/uploader";
import { API_V1_LOGOUT } from "./urls";
import Button from "./bootstrap/button";


const SidebarProfileAccordion = {
  oninit(vnode) {
    vnode.state.show = false;
  },

  view(vnode) {
    return (
      m(".accordion",
        m(".accordion-item", [
          m("h2.accordion-header", {
              "aria-expanded": String(vnode.state.show),
            }, m("button.accordion-button[type=button][aria-controls=profileAccordion]", {
              class: vnode.state.show ? "" : "collapsed",
              onclick: () => { vnode.state.show = !vnode.state.show }
            }, "Account")
          ),
          m(Collapse, {
              collapsed: !vnode.state.show,
              id: "profileAccordion",
              class: "accordion-collapse",
            }, m("div", [
              m("ul.list-group list-group-flush", [
                m("li.list-group-item", m(Button, {
                  selector: "button",
                  class: "nav-link text-danger",
                  onclick: () => {
                    m.request({
                      method: "POST",
                      url: API_V1_LOGOUT,
                    }).then(() => {
                      window.location.href = "/";
                    }).catch(err => {
                      console.error("Logout failed", err);
                    });
                  },
                }, "Logout")),
              ]),
            ])
          )
        ])
      )
    )
  }
};

// Sidebar on left side of dashboard - only for md width
const DashboardSideBar = {
  view(vnode) {
    return (
      m(".app-sidebar vh-100 overflow-y-auto p-3 d-md-flex d-none flex-column border-end bg-light", [
        // Title
        m("a[href=/].d-flex align-items-center mb-3 mb-md-0 text-dark me-md-auto text-decoration-none",
          m("span.fs-4", "Polyfile"),
        ),

        // Upload and Create Buttons
        m(".pt-3 border-top", [
          m("label.btn btn-primary w-100 mb-2", [
            m("span.fa fa-upload[aria-hidden=true]"), " ", "Upload",
            m("input.d-none[type=file]", { onchange: uploadFile }),
          ]),
          m("button.btn btn-outline-secondary w-100", {
            onclick: () => showModal(CreateDirectoryModalComponent.modalId),
          }, [m("span.fa fa-folder-plus[aria-hidden=true]"), " ", "Create"]),
        ]),

        m("hr"),

        // Navigation Links
        m("ul.nav nav-pills flex-column mb-auto", (vnode.attrs.items || []).map((item) => (
          m("li.nav-item", { key: item.id }, m(NavLink, {
            href: item.url,
            class: vnode.attrs.activeId === item.id ? "bg-primary-subtle text-primary-emphasis" : ""
          }, item.name))
        ))),

        // Account Menu
        m(".mt-3 pt-3 border-top mt-auto", m(SidebarProfileAccordion)),
      ])
    );
  }
};

export default DashboardSideBar;
