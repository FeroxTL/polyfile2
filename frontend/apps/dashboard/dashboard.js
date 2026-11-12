// Bootstrap is already imported in "vendor" css
import m from "mithril";
import { FILES_DASHBOARD_URL } from "./constants/endpoints";
import { showModal } from "./bootstrap/modal";
import RemoveFsNodeModalComponent from "./modals/remove_fsnode_modal";
import { ShareDirectoryModal } from "./modals/share_directory_modal";
import { DashboardFsNodeList } from "./services/DashboardFsNodeList";
import { DashboardFsNodeListView } from "./components/DashboardFsNodeListView";
import { DashboardFsNodeActionbarView } from "./components/DashboardFsNodeActionbarView";
import { DashboardShell } from "./components/DashboardShell";
import { ArchiveDownloadModal } from "@polyfile/core/components/ArchiveDownloadModal";
import { BreadcrumbsView } from "@polyfile/core/components/BreadcrumbsView";
import { FolderDownloadButton } from "@polyfile/core/components/FolderDownloadButton";
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

const openArchiveDownloadModal = (fsNode) => {
  showModal(ArchiveDownloadModal, {
    downloadUrl: fsNode.download_url,
    name: fsNode.name,
  });
};

const DashboardNavigationHandler = (path, name) => {
  m.route.set(FILES_DASHBOARD_URL, {
    path: joinPath(path, name)
  });
};

const DashboardView = {
  view() {
    const selectedList = DashboardFsNodeList.elements.filter(item => item.selected);

    return m(DashboardShell, [
      selectedList.length > 0
        ? m(".card.text-bg-dark.sticky-top", m(".card-body.p-2.ps-3", m(DashboardFsNodeActionbarView, {
          selectedList,
          onClose: () => DashboardFsNodeList.selectFsNode(),
          onShare: openShareModal,
          onRemove: () => showModal(RemoveFsNodeModalComponent),
          onDownload: openArchiveDownloadModal,
        })))
        : m(BreadcrumbsView, {
          FsNodeList: DashboardFsNodeList,
          getPublicUrl: (path) => m.buildPathname(FILES_DASHBOARD_URL, {
            path: joinPath("/", path),
          }),
          actions: m(FolderDownloadButton, {
            fsNode: DashboardFsNodeList.current,
            onDownload: openArchiveDownloadModal,
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
