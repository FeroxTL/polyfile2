// Bootstrap is already imported in "vendor" css
import m from "mithril";
import { FILES_DASHBOARD_URL } from "./constants/endpoints";
import { showModal } from "./bootstrap/modal";
import { RemoveFsNodeModalComponent } from "./modals/RemoveFsNodeModal";
import { RenameFsNodeModal } from "./modals/RenameFsNodeModal";
import { ShareDirectoryModal } from "./modals/ShareDirectoryModal";
import { DashboardFsNodeList } from "./services/DashboardFsNodeList";
import { DashboardFsNodeListView } from "./components/DashboardFsNodeListView";
import { DashboardFsNodeActionbarView } from "./components/DashboardFsNodeActionbarView";
import { DashboardShell } from "./components/DashboardShell";
import { ArchiveDownloadModal } from "@polyfile/core/components/ArchiveDownloadModal";
import { BreadcrumbsView } from "@polyfile/core/components/BreadcrumbsView";
import { FolderDownloadButton } from "@polyfile/core/components/FolderDownloadButton";
import { joinPath, normalizePath } from "@polyfile/core/utils/urls";

const openShareModal = (fsNode) => {
  showModal(ShareDirectoryModal, {
    share: fsNode.share,
    nodeId: fsNode.id,
    type: fsNode.type,
    onUpdate: (shareData) => {
      fsNode.share = shareData;
    },
  });
};

const openRenameModal = (fsNode) => {
  showModal(RenameFsNodeModal, { fsNode });
};

const openArchiveDownloadModal = (fsNode) => {
  showModal(ArchiveDownloadModal, {
    downloadUrl: fsNode.download_url,
    name: fsNode.name,
  });
};

/**
 * Preload a known directory by UUID so the route handler skips the path lookup.
 */
const preloadPath = (fsNode, targetPath) => {
  if (fsNode?.id) {
    DashboardFsNodeList.loadByNodeId(fsNode.id, normalizePath(targetPath));
  }
};

const dashboardNavigationHandler = (path, name, fsNode) => {
  const targetPath = normalizePath(joinPath(path, name));
  preloadPath(fsNode, targetPath);
  m.route.set(FILES_DASHBOARD_URL, {
    path: targetPath
  });
};

const dashboardBreadcrumbHandler = (fsNode, path) => preloadPath(fsNode, path);

const DashboardView = {
  view() {
    const selectedList = DashboardFsNodeList.elements.filter(item => item.selected);

    return m(DashboardShell, [
      selectedList.length > 0
        ? m(".card.text-bg-dark.sticky-top", m(".card-body.p-2.ps-3", m(DashboardFsNodeActionbarView, {
          selectedList,
          onClose: () => DashboardFsNodeList.selectFsNode(),
          onShare: openShareModal,
          onRename: openRenameModal,
          onRemove: () => showModal(RemoveFsNodeModalComponent),
          onDownload: openArchiveDownloadModal,
        })))
        : m(BreadcrumbsView, {
          FsNodeList: DashboardFsNodeList,
          getPublicUrl: (path) => m.buildPathname(FILES_DASHBOARD_URL, {
            path: joinPath("/", path),
          }),
          onNavigate: dashboardBreadcrumbHandler,
          actions: m(FolderDownloadButton, {
            fsNode: DashboardFsNodeList.current,
            onDownload: openArchiveDownloadModal,
          }),
        }),

      m(DashboardFsNodeListView, {
        fsnodeList: DashboardFsNodeList,
        header: m("h4.mb-3", "Files & Directories"),
        navigationHandler: dashboardNavigationHandler,
        onShareClick: openShareModal,
      }),
    ]);
  },
};

// Export the components for use in tests and Mithril's mount function
export { DashboardView, dashboardNavigationHandler, dashboardBreadcrumbHandler };
