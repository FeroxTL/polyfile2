// Bootstrap is already imported in "vendor" css
import m from "mithril";
import DashboardSideBar from "./sidebar";
import DashboardNavBar from "./navbar";
import { API_V1_FSNODE, DEFAULT_ROOT_URL, FILES_DASHBOARD_URL } from "./urls";
import { ModalBackdrop, showModal } from "./bootstrap/modal";
import CreateDirectoryModalComponent from "./modals/create_directory_modal";
import RemoveFsNodeModalComponent from "./modals/remove_fsnode_modal";
import { uploadFile } from "./modals/uploader";
import Card from "./bootstrap/card";


const XHR_READY_STATE_DONE = 4;


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

/**
  Available sorters.
 */
const Sorters = {
  default: (a, b) => {
    if (a.type === "directory" && b.type !== "directory") {return -1;}
    if (a.type !== "directory" && b.type === "directory") {return 1;}
    return a.name.localeCompare(b.name);
  },
};


// File list data
const FsNodeList = {
  current: null,
  elements: [],
  error: null,
  xhr: null,
  // Function to load data using m.request
  load(path) {
    if (this.xhr !== null) {this.xhr.abort();}

    return m.request({
      method: "GET",
      url: API_V1_FSNODE,
      params: {path: path || ""},
      config: (xhr) => {this.xhr = xhr},
    })
    .then((data) => {
      this.error = null;
      this.current = new FsNode(data.current);
      const sorter = Sorters[this.current.sorting || "default"];
      this.elements = data.children.map((child) => new FsNode(child)).sort(sorter);
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
      item.selected = (item === fsNode)
    });
  },

  /**
    Add FsNode respecting sorting
   */
  addFsNode(fsNode) {
    const sorter = Sorters[this.current.sorting || "default"];
    for (let i = 0; i < this.elements.length; i++) {
      if (sorter(this.elements[i], fsNode) > 0) {
        this.elements.splice(i, 0, fsNode);
        return;
      }
    };
    this.elements.push(fsNode);
  },
};

// FsNode breadcrumbs component
const FsNodeListBreadcrumbsComponent = {
  view() {
    if (FsNodeList.current === null) {return null};

    return (
      m("nav[aria-label=breadcrumb]",
        m("ol.breadcrumb mb-0", FsNodeList.current.path.split("/").map((item, index, array) => {
          const isLast = index === array.length - 1,
           itemName = index === 0 ? "Files" : item,
           url = encodeURIComponent(`/disk${  array.slice(0, index + 1).join("/")}`).replaceAll("%2F", "/");
          return m("li.breadcrumb-item", {
            class: isLast ? "active" : null,
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
};

// Available actions for the selected item
const FsNodeActionbarComponent = {
  view() {
    const selectedList = FsNodeList.elements.filter(item => item.selected);
    const selectedItem = selectedList.length === 1 ? selectedList[0] : null;

    return (
      m(".row app-ignore-selection", [
        m(".col py-2 text-nowrap overflow-hidden", m("span",
          selectedList.length === 1
            && m("span", m("i.h5 mb-0 fa d-none d-lg-inline", { class: selectedItem.type === "directory" ? "fa-folder" : "fa-file" }), [" ", selectedItem.name])
            || `Selected ${  selectedList.length  } items`
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

  navigate(fsNode, event) {
    if (fsNode.type !== "file") {
      m.route.set(FILES_DASHBOARD_URL, {key: encodeURIComponent(`${FsNodeList.current.path  }/${  fsNode.name}`).replaceAll("%2F", "/")});
    };
    event.preventDefault();
    return false;
  },

  view() {
    if (FsNodeList.error !== null) {
      let errorMessage = FsNodeList.error.message;
      if (FsNodeList.error.code === 0) {
        errorMessage = "Unknown error, please try again later";
      } else if (FsNodeList.error.response && FsNodeList.error.response.detail) {
        errorMessage = FsNodeList.error.response.detail;
      }

      return m(Card, { class: "w-50 align-self-center mt-5 bg-warning" }, [
        m("p.card-text", errorMessage),
        (FsNodeList.error.code === 0) &&
          m("a", { href: "#", class: "btn btn-primary me-2", onclick: () => window.location.reload() }, "Refresh page") ||
          m(m.route.Link, { href: DEFAULT_ROOT_URL, class: "btn btn-primary me-2" }, "Main page"),
      ]);
    }

    if (FsNodeList.xhr !== null && FsNodeList.xhr.readyState !== XHR_READY_STATE_DONE) {
      return m("div.flex-grow-1", [
        m(FsNodeListBreadcrumbsComponent),
        // TODO: Add loading placeholders https://getbootstrap.com/docs/5.2/components/placeholders/
        m("p", "Loading.."),
      ])
    };

    return (
      m("div.flex-grow-1 my-md-2 my-1", [

        FsNodeList.elements.filter(item => item.selected).length > 0
          && m(".card mb-2 text-bg-dark sticky-top", m(".card-body p-2", m(FsNodeActionbarComponent)))
          || m(".card mb-2", m(".card-body", m(FsNodeListBreadcrumbsComponent))),

        (FsNodeList.elements.length === 0) && m(FsNodeEmptyDirectoryComponent),

        m("ul.list-group user-select-none", FsNodeList.elements.map((item) => (
          m("li[role=button].list-group-item list-group-item-action list-group-item-light py-3 d-flex justify-content-between", {
            key: item.name,
            class: item.selected ? "active" : null,
            'aria-current': item.selected ? String(item.selected) : null,
            onclick: (e) => {
              e.preventDefault();
              e.stopPropagation();
              FsNodeList.selectFsNode(item);
            },
            ondblclick: this.navigate.bind(null, item),
          }, [
            m("span", m("i.h4 mb-0 fa", { class: item.type === "directory" ? "fa-folder" : "fa-file" })),
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
    // TODO: how to get? from url?
    vnode.state.activeId = window.location.pathname.split("/")[1] || "files";
  },

  view(vnode) {
    const sidebarUrls = JSON.parse(document.getElementById("dashboard-urls").textContent) ;

    return [
      m(".d-flex w-100", [
        m(DashboardSideBar, { activeId: vnode.state.activeId, items: sidebarUrls }),
        m(".flex-grow-1 vh-100 overflow-y-auto bg-light",
          m(".container-fluid", [
             m(DashboardNavBar, { activeId: vnode.state.activeId, items: sidebarUrls }),
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
