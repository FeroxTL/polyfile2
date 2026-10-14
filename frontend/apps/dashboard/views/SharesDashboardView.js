import m from "mithril";
import { DashboardShell } from "../components/DashboardShell";
import { ShareList } from "../services/ShareList";
import { showPermanentDeleteShareModal } from "../modals/permanent_delete_share_modal";
import { FILES_DASHBOARD_URL } from "../constants/endpoints";
import { showModal } from "../bootstrap/modal";
import { ShareDirectoryModal } from "../modals/share_directory_modal";
import Button from "@polyfile/core/ui-kit/button";

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "revoked", label: "Revoked" },
  { value: "expired", label: "Expired" },
];

const formatDate = (value) => {
  if (!value) {
    return null;
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

const getNodeName = (share) => share?.root_fs_node?.name || "—";
const getNodeType = (share) => share?.root_fs_node?.type || "—";
const getNodePath = (share) => share?.root_fs_node?.path || null;

const SharesDashboardView = {
  oninit(vnode) {
    vnode.state.service = ShareList;
    vnode.state.service.load({ status: "all", page: 1, pageSize: 25 }).catch(() => null);
  },

  setStatus(vnode, status) {
    vnode.state.service
      .load({ status, page: 1, pageSize: vnode.state.service.pageSize })
      .catch(() => null);
  },

  getParentPath(path) {
    if (!path || path === "/") {
      return "/";
    }
    const trimmed = path.replace(/\/$/u, "");
    const index = trimmed.lastIndexOf("/");
    if (index <= 0) {
      return "/";
    }
    return trimmed.slice(0, index);
  },

  navigateToNode(share) {
    const path = getNodePath(share);
    if (!path) {
      return;
    }
    if (getNodeType(share) === "directory") {
      m.route.set(FILES_DASHBOARD_URL, { key: path });
      return;
    }
    m.route.set(FILES_DASHBOARD_URL, { key: this.getParentPath(path) });
  },

  revokeShare(vnode, share) {
    const { service } = vnode.state;
    service.revoke(share)
      .then(() => service.load({ status: service.status, page: service.page, pageSize: service.pageSize }))
      .catch(() => null);
  },

  deleteShare(vnode, share) {
    const { service } = vnode.state;
    showPermanentDeleteShareModal({
      share,
      onConfirm: () => service.deletePermanent(share)
        .then(() => service.load({ status: service.status, page: service.page, pageSize: service.pageSize })),
    });
  },

  renderFilters(vnode, service) {
    return m(".mb-3", [
      m(".btn-group", STATUS_OPTIONS.map((option) =>
        m("button.btn", {
          class: service.status === option.value ? "btn-primary" : "btn-outline-primary",
          onclick: () => this.setStatus(vnode, option.value),
        }, option.label)
      )),
    ]);
  },

  openShareModal(vnode, share) {
    const nodePath = getNodePath(share);

    showModal(ShareDirectoryModal, {
      share,
      path: nodePath,
      type: getNodeType(share),
      onUpdate: (data) => {
        Object.assign(share, {
          url: data?.url || null,
          expires_at: data?.expires_at || null,
          revoked_at: data === null ? new Date().toISOString() : data.revoked_at,
          status: data?.status || "revoked",
        });
      },
    });
  },

  renderTimeline(share) {
    const created = formatDate(share.created_at);
    const ends = formatDate(share.revoked_at) || formatDate(share.expires_at);
    if (ends) {
      return `${created} - ${ends}`;
    }
    return created;
  },

  renderStatusButton(vnode, share) {
    return m(Button, {
      type: "button",
      class: "btn-sm btn-outline-secondary",
      onclick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.openShareModal(vnode, share);
      },
    }, share.status || "—");
  },

  renderDownloads(share) {
    const count = typeof share.download_count === "number" ? share.download_count : 0;
    return m("span.d-none.d-sm-inline-flex align-items-center", [
      m("i.fa fa-download me-1[aria-hidden=true]"),
      count,
    ]);
  },

  renderItem(vnode, share) {
    const name = getNodeName(share);
    const type = getNodeType(share);
    const iconClass = type === "directory" ? "fa-folder" : "fa-file";

    return m("li[role=button].list-group-item list-group-item-action list-group-item-light py-2 d-flex align-items-center flex-nowrap", {
      key: share.id,
      ondblclick: (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.navigateToNode(share);
      },
    }, [
      m("span.fsnode-icon me-2 flex-shrink-0", m("i.h5 mb-0 fa", { class: iconClass })),
      m("span.flex-grow-1 text-truncate", { title: name, style: "min-width: 0;" }, name),
      m(".d-flex align-items-center flex-nowrap gap-1 justify-content-end flex-shrink-0 text-nowrap", [
        m("span.d-none d-lg-inline-block", this.renderTimeline(share)),
        this.renderDownloads(share),
        this.renderStatusButton(vnode, share),
        m(Button, {
          type: "button",
          class: "btn-sm btn-outline-danger",
          title: "Delete permanently",
          onclick: (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.deleteShare(vnode, share);
          },
        }, m("i.fa fa-trash[aria-hidden=true]")),
      ]),
    ]);
  },

  renderList(vnode, service) {
    const items = service.items || [];

    return m("ul.list-group user-select-none", items.length
      ? items.map((share) => this.renderItem(vnode, share))
      : [m("li.list-group-item text-center text-muted", "No public links found.")]);
  },

  view(vnode) {
    const { service } = vnode.state;

    return m(DashboardShell, [
      m(".container-fluid p-3 p-md-4", [
        m(".d-flex justify-content-between align-items-center mb-3", [
          m("h4.mb-0", "Public links"),
        ]),
        this.renderFilters(vnode, service),
        service.isLoading && m(".text-muted", "Loading..."),
        service.error && m(".alert alert-danger", "Failed to load public links."),
        !service.isLoading && !service.error && this.renderList(vnode, service),
      ]),
    ]);
  },
};

export { SharesDashboardView };
