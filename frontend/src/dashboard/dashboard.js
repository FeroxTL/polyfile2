// Bootstrap is already imported in "vendor" css
import m from "mithril";
import DashboardSideBar from "./sidebar";
import DashboardNavBar from "./navbar";
import { API_V1_FSNODE, DASHBOARD_ROOT_URL } from "./urls";
import { ModalBackdrop, showModal } from "./bootstrap/modal";
import CreateDirectoryModalComponent from "./modals/create_directory_modal";
import RemoveFsNodeModalComponent from "./modals/remove_fsnode_modal";
import { uploadFile } from "./modals/uploader";


// FsNode model
function FsNode(data) {
  this.name = data.name || "";
  this.type = data.type || "";
  this.created_at = data.created_at || null;
  this.modified_at = data.modified_at || null;
  this.size = data.size || 0;
  this.mime_type = data.mime_type || "";
  this.md5 = data.md5 || "";
  this.file = data.file || "";
  this.path = data.path || "";
  this.download_url = data.download_url || "";
  this.selected = false;
};

// File list data
const FsNodeList = {
  current: null,
  elements: [],
  error: null,
  xhr: null,
  // Function to load data using m.request
  load(path) {
    if (this.xhr !== null) this.xhr.abort();

    return m.request({
      method: "GET",
      url: API_V1_FSNODE,
      params: {path: path || ""},
      config: (xhr) => {this.xhr = xhr},
    })
    .then((data) => {
      this.error = null;
      this.current = new FsNode(data.current);
      this.elements.length = 0;
      data.children.map((child) => (this.elements.push(new FsNode(child))));
    })
    .catch(error => {
      FsNodeList.error = error;
    }).finally(() => {
      this.xhr = null;
    });
  },

  selectFsNode(fsNode) {
    // Select fs_node and remove selection from others
    FsNodeList.elements.forEach((item) => {
      item.selected = (item == fsNode)
    });
  },
};

// FsNode breadcrumbs component
const FsNodeListBreadcrumbsComponent = {
  view() {
    if (FsNodeList.current == null) {return};

    return (
      m("nav[aria-label=breadcrumb]",
        m("ol.breadcrumb mb-0", FsNodeList.current.path.split("/").map((item, index, array) => {
          const isLast = index === array.length - 1;
          const itemName = index === 0 ? "Files" : item;
          const url = encodeURIComponent("/disk" + array.slice(0, index + 1).join("/")).replaceAll("%2F", "/");
          return m("li.breadcrumb-item", {
            class: isLast ? "active" : undefined,
          }, isLast ? itemName : m(m.route.Link, { href: url }, itemName))
        }))
      )
    )
  }
};

// Empty directory component
const FsNodeEmptyDirectoryComponent = {
  view() {
    return (
      m(".row",
        m(".col-md-10 offset-md-1 col-lg-8 .offset-lg-2",
          m(".card text-center mt-2", [
            m("p.card-header bg-primary", "This directory is empty"),
            m(".card-body border border-primary p-4", [
              m("p.card-text text-secondary", "Select files to upload"),
              m("label.btn btn-primary", [
                m("span.fa fa-upload[aria-hidden=true]"), " ", "Upload",
                m("input.d-none[type=file]", { onchange: uploadFile }),
              ]),
            ])
          ])
        )
      )
    )
  }
}

// Available actions for the selected item
const FsNodeActionbarComponent = {
  view() {
    const selectedList = FsNodeList.elements.filter(item => item.selected);
    const selectedItem = selectedList.length == 1 ? selectedList[0] : null;

    return (
      m(".row app-ignore-selection", [
        m(".col py-2 text-nowrap overflow-hidden", m("span",
          selectedList.length == 1
            && m("span", m("i.h5 mb-0 fa d-none d-lg-inline", { class: selectedItem.type == "directory" ? "fa-folder" : "fa-file" }), [" ", selectedItem.name])
            || "Selected " + selectedList.length + " items"
        )),
        // TODO: tooltip?
        // TODO: m(Button) ?
        // TODO: implement
        m(".col d-flex justify-content-end col-auto", [
          m("a.btn btn-outline-light me-md-2", {
            class: selectedItem && selectedItem.download_url ? "" : "disabled",
            href: m.buildPathname(selectedItem.download_url || "#", {
              disposition: "attachment",
            }),
            title: "Download",
          }, [m("span.fa fa-download[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Download")]),
          m("a.btn btn-outline-light me-md-2 disabled", {
            title: "Share",
            disabled: true,
          }, [m("span.fa fa-share[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Share")]),
          m("a.btn btn-outline-light me-md-2 disabled", {
            title: "Rename",
            disabled: true,
          }, [m("span.fa fa-edit[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Rename")]),
          m("a.btn btn-outline-light me-md-2 disabled", {
            title: "Move",
            disabled: true,
          }, [m("span.fa fa-arrow-right-arrow-left[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Move")]),
          m("a.btn btn-outline-light me-md-2", {
            title: "Remove",
            onclick: () => { showModal(RemoveFsNodeModalComponent.modalId); },
          }, [m("span.fa fa-trash[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Remove")]),
          m("a.btn btn-outline-light", {
            title: "Close",
            onclick: () => {FsNodeList.selectFsNode()},
          }, m("span.fa fa-close[aria-hidden=true]")),
        ]),
      ])
    )
  }
};

// FsNode list component
const FsNodeListComponent = {
  onDocumentClick(e) {
   // Remove selection from all fs_nodes
   if (e.target.closest(".app-ignore-selection")) {
     return;
   }
   FsNodeList.selectFsNode();
   m.redraw();
  },

  oncreate() {
    document.addEventListener("click", this.onDocumentClick);
  },

  onremove() {
    document.removeEventListener("click", this.onDocumentClick);
  },

  navigate(fs_node, event) {
    if (fs_node.type != "file") {
      m.route.set(DASHBOARD_ROOT_URL, {key: encodeURIComponent(FsNodeList.current.path + "/" + fs_node.name).replaceAll("%2F", "/")});
    };
    event.preventDefault();
    return false;
  },

  view() {
    if (FsNodeList.error != null) {
      let errorMessage = FsNodeList.error.message;
      if (FsNodeList.error.code == 0) {
        errorMessage = "Unknown error, please try again later";
      } else if (FsNodeList.error.response && FsNodeList.error.response.detail) {
        errorMessage = FsNodeList.error.response.detail;
      }

      return (
        m(".card w-50 align-self-center mt-5 bg-warning", [
          m(".card-header", "Error"),
          m(".card-body", [
            m("p.card-text", errorMessage),
            (FsNodeList.error.code == 0) &&
              m("a", {href: "#", class: "btn btn-primary me-2", onclick: () => window.location.reload()}, "Refresh page") ||
              m(m.route.Link, {href: "/disk/", class: "btn btn-primary me-2"}, "Main page"),
          ])
        ])
      )
    }

    if (FsNodeList.xhr !== null && FsNodeList.xhr.readyState != 4) {
      return m("div.flex-grow-1", [
        m(FsNodeListBreadcrumbsComponent),
        m("p", "Loading.."), // TODO: Add loading placeholders https://getbootstrap.com/docs/5.2/components/placeholders/
      ])
    };

    return (
      m("div.flex-grow-1 my-md-2 my-1", [

        FsNodeList.elements.filter(item => item.selected).length > 0
          && m(".card mb-2 text-bg-dark sticky-top", m(".card-body p-2", m(FsNodeActionbarComponent)))
          || m(".card mb-2", m(".card-body", m(FsNodeListBreadcrumbsComponent))),

        (FsNodeList.elements.length == 0) && m(FsNodeEmptyDirectoryComponent),

        m("ul.list-group user-select-none", FsNodeList.elements.map((item) => (
          m("li[role=button].list-group-item list-group-item-action list-group-item-light py-3 d-flex justify-content-between", {
            key: item.name,
            class: item.selected ? "active" : null,
            'aria-current': item.selected ? String(item.selected) : undefined,
            onclick: (e) => {
              e.preventDefault();
              e.stopPropagation();
              FsNodeList.selectFsNode(item);
            },
            ondblclick: this.navigate.bind(null, item),
          }, [
            m("span", m("i.h4 mb-0 fa", { class: item.type == "directory" ? "fa-folder" : "fa-file" })),
            m("span.flex-grow-1 ms-2", item.name),
            m("span.d-none .d-sm-block", item.type),
          ])
        )))
      ])
    );
  }
};

const DashboardView = {
  oninit(vnode) {
    FsNodeList.load(vnode.attrs.key);
    vnode.state.activeId = "files";  // TODO: how to get? from url?
  },

  view(vnode) {
    const sidebarUrls = JSON.parse(document.getElementById("dashboard-urls").textContent) ;

    return [
      m(".d-flex w-100", [
        m(DashboardSideBar, { items: sidebarUrls, activeId: vnode.state.activeId }),
        m(".flex-grow-1 vh-100 overflow-y-auto bg-light",
          m(".container-fluid", [
             m(DashboardNavBar, { items: sidebarUrls, activeId: vnode.state.activeId }),
             m(FsNodeListComponent),
          ])
        ),
      ]),

      // Modals
      // Create directory modal
      m(CreateDirectoryModalComponent),
      // Remove FsNode modal
      m(RemoveFsNodeModalComponent),
      // Modal backdrop
      m(ModalBackdrop),
    ]
  },
};

// Export the component for use in Mithril's mount function
export default DashboardView;
export { FsNodeList, FsNode };
