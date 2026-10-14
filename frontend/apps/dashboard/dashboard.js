// Bootstrap is already imported in "vendor" css
import m from "mithril";
import { API_V1_FSNODE, FILES_DASHBOARD_URL } from "./constants/endpoints";
import { showModal } from "./bootstrap/modal";
import RemoveFsNodeModalComponent from "./modals/remove_fsnode_modal";
import { ShareDirectoryModal } from "./modals/share_directory_modal";
import { DashboardFsNodeList } from "./services/DashboardFsNodeList";
import { DashboardFsNodeListView } from "./components/DashboardFsNodeListView";
import { DashboardShell } from "./components/DashboardShell";
import { BreadcrumbsView } from "@polyfile/core/components/BreadcrumbsView";
import { joinPath } from "@polyfile/core/utils/urls";

const openShareModal = (fsNode) => {
  const path = joinPath(DashboardFsNodeList.current.path, fsNode.name);
  showModal(ShareDirectoryModal, {
    share: fsNode.share,
    path,
    type: fsNode.type,
    onUpdate: (shareData) => {
      fsNode.share = shareData;
    },
  });
};

// Available actions for the selected item
const FsNodeActionbarComponent = {
  view() {
    const selectedList = DashboardFsNodeList.elements.filter(item => item.selected);
    const selectedItem = selectedList.length === 1 ? selectedList[0] : null;

    return (
      m(".row app-ignore-selection", [
        m(".col py-2 text-nowrap overflow-hidden", m("span",
          selectedList.length === 1
            && m("span", m("i.h5 mb-0 fa d-none d-lg-inline", { class: selectedItem.type === "directory" ? "fa-folder" : "fa-file" }), [" ", selectedItem.name])
            || `Selected ${selectedList.length} items`
        )),
        // TODO: tooltip?
        // TODO: m(Button) ?
        // TODO: implement
        m(".col d-flex justify-content-end col-auto", [
          m("a.btn btn-outline-light me-md-2", {
            class: selectedItem && selectedItem.download_url ? "" : "disabled",
            href: m.buildPathname(selectedItem?.download_url || "#", {
              disposition: "attachment",
            }),
            title: "Download",
          }, [m("span.fa fa-download[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Download")]),
          m("a.btn btn-outline-light me-md-2", {
            title: "Share",
            disabled: !selectedItem,
            onclick: (e) => {
              e.preventDefault();
              if (selectedItem) {
                openShareModal(selectedItem);
              }
            },
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
            onclick: () => { showModal(RemoveFsNodeModalComponent) },
          }, [m("span.fa fa-trash[aria-hidden=true]"), " ", m("span.d-lg-inline-block d-none", "Remove")]),
          m("a.btn btn-outline-light", {
            title: "Close",
            onclick: () => { DashboardFsNodeList.selectFsNode() },
          }, m("span.fa fa-close[aria-hidden=true]")),
        ]),
      ])
    );
  }
};


const DashboardNavigationHandler = (path, name) => {
  m.route.set(FILES_DASHBOARD_URL, {
    key: joinPath(path, name)
  });
};

const DashboardView = {
  oninit(vnode) {
    DashboardFsNodeList.load(API_V1_FSNODE, { path: vnode.attrs.key });
  },

  view() {
    return m(DashboardShell, [
      DashboardFsNodeList.elements.some(item => item.selected) &&
        m(".card text-bg-dark sticky-top", m(".card-body p-2 ps-3", m(FsNodeActionbarComponent))) ||
        m(BreadcrumbsView, {
          FsNodeList: DashboardFsNodeList,
          getPublicUrl: (path) => m.buildPathname(FILES_DASHBOARD_URL, {
            key: joinPath("/", path),
          }),
        }),

      m(DashboardFsNodeListView, {
        fsnodeList: DashboardFsNodeList,
        header: m("h4.mb-3", "Files & Directories"),
        navigationHandler: DashboardNavigationHandler,
        onShareClick: openShareModal,
      }),
    ]);
  },
};

// Export the component for use in Mithril's mount function
export { DashboardView };
