import m from "mithril";

import { FsNodeList } from "@polyfile/core/services/FsNodeList";
import Button from "@polyfile/core/ui-kit/button";
import { Modal, closeModal } from "../bootstrap/modal";
import { API_V1_FSNODE, API_V1_FSNODE_BY_ID } from "../constants/endpoints";
import { DashboardFsNode } from "../models/DashboardFsNode";
import { DashboardFsNodeList } from "../services/DashboardFsNodeList";
import { getApiErrorDetail } from "./Errors";

/**
 * Directory rows shown by the move picker.
 *
 * @param {FsNodeList} list - Loaded picker list.
 * @returns {Array} Directory nodes only.
 */
const getDirectories = (list) => (
  list.elements.filter((node) => node.type === "directory")
);

/**
 * Breadcrumb items for the picker location.
 *
 * The virtual root is always the first item and is active while no real
 * directory is loaded. The active item is derived from the node id rather
 * than from its position, so a node repeated in `ancestors` stays active
 * instead of turning into a link to itself.
 *
 * @param {FsNodeList} fsNodeList - Listing whose `current` and `ancestors`
 *   describe the directory displayed by the picker.
 * @returns {Array<{id: string|null, name: string, active?: boolean}>} Items.
 */
const getBreadcrumbItems = (fsNodeList) => {
  const { current } = fsNodeList;
  const ancestors = fsNodeList.ancestors || [];
  const currentId = current?.id ?? null;
  const items = [{ id: null, name: "Files", active: currentId === null }];

  ancestors.forEach((ancestor) => {
    items.push({
      id: ancestor.id,
      name: ancestor.name,
      active: currentId !== null && ancestor.id === currentId,
    });
  });

  const currentListed = ancestors.some((ancestor) => ancestor.id === currentId);
  if (currentId !== null && !currentListed) {
    items.push({
      id: currentId,
      name: current.name,
      active: true,
    });
  }

  return items;
};

/**
 * Destination id selected in the picker.
 *
 * @param {Object} vnode - Modal vnode.
 * @returns {string|null} Directory UUID, or `null` for the virtual root.
 */
const getTargetId = (vnode) => vnode.state.fsNodeList.current?.id ?? null;

/**
 * Whether the selected destination is a meaningful move target.
 *
 * Descendant checks stay on the backend; this only hides the obvious no-op
 * and self-move cases.
 *
 * @param {Object} vnode - Modal vnode.
 * @returns {boolean} True when "Move here" can be submitted.
 */
const canMoveHere = (vnode) => {
  const { fsNode, fsNodeList, loading } = vnode.state;
  if (!fsNode || loading || !fsNodeList.current) {
    return false;
  }

  const targetId = getTargetId(vnode);
  return targetId !== fsNode.id && targetId !== (fsNode.parent_id ?? null);
};

/**
 * Load the virtual root or a directory into the picker list.
 *
 * @param {Object} vnode - Modal vnode.
 * @param {string|null} nodeId - Directory UUID; `null` loads the virtual root.
 * @returns {Promise<void>}
 */
const loadDirectory = (vnode, nodeId) => {
  const { fsNodeList } = vnode.state;
  vnode.state.error = null;
  vnode.state.loading = true;

  const request = nodeId
    ? fsNodeList.load(m.buildPathname(API_V1_FSNODE_BY_ID, { id: nodeId }), {})
    : fsNodeList.load(API_V1_FSNODE, { path: "/" });

  return request.then(() => {
    vnode.state.loading = false;
    vnode.state.error = fsNodeList.error;
  }, (error) => {
    vnode.state.loading = false;
    vnode.state.error = error;
  });
};

/**
 * Move the node to the directory currently selected in the picker.
 *
 * @param {Object} vnode - Modal vnode.
 * @returns {Promise<void>}
 */
const sendMoveFsNodeRequest = (vnode) => {
  vnode.state.error = null;
  if (!canMoveHere(vnode)) {
    return Promise.resolve();
  }

  return DashboardFsNodeList.moveFsNode(vnode.state.fsNode, getTargetId(vnode)).then(
    () => {
      closeModal(vnode.attrs.modalId);
    },
    (error) => {
      vnode.state.error = error;
    },
  );
};

const renderBreadcrumbs = (vnode) => {
  const items = getBreadcrumbItems(vnode.state.fsNodeList);

  return m(
    "nav[aria-label=breadcrumb]",
    m("ol.breadcrumb.mb-0", items.map((item) => m(
      "li.breadcrumb-item",
      { class: item.active ? "active" : null },
      item.active
        ? item.name
        : m("a", {
          href: "#",
          onclick: (event) => {
            event.preventDefault();
            loadDirectory(vnode, item.id);
          },
        }, item.name),
    ))),
  );
};

const renderDirectories = (vnode) => {
  const { fsNodeList, fsNode } = vnode.state;
  const directories = getDirectories(fsNodeList);

  if (directories.length === 0) {
    return m(".text-muted", "No subdirectories");
  }

  return m(".list-group.list-group-flush", directories.map((directory) => {
    const isMovedNode = directory.id === fsNode.id;

    return m(
      "button.list-group-item.list-group-item-action.d-flex.align-items-center.gap-2",
      {
        type: "button",
        disabled: isMovedNode,
        title: isMovedNode ? "Cannot move a directory into itself" : directory.name,
        onclick: () => {
          if (!isMovedNode) {
            loadDirectory(vnode, directory.id);
          }
        },
      },
      [
        m("span.fa.fa-folder[aria-hidden=true]"),
        m("span.flex-grow-1.text-start", directory.name),
        m("span.fa.fa-chevron-right[aria-hidden=true]"),
      ],
    );
  }));
};

const renderFooter = (vnode, canSubmit) => m(".modal-footer", [
  m(Button, {
    type: "button",
    class: "btn-secondary",
    onclick: () => closeModal(vnode.attrs.modalId),
  }, "Cancel"),
  m(Button, {
    type: "submit",
    disabled: !canSubmit,
  }, "Move here"),
]);

const MoveFsNodeModal = {
  oninit(vnode) {
    vnode.state.fsNode = vnode.attrs.fsNode
      || DashboardFsNodeList.elements.find((item) => item.selected)
      || null;
    vnode.state.fsNodeList = new FsNodeList(DashboardFsNode);
    vnode.state.loading = false;
    vnode.state.error = null;

    loadDirectory(vnode, null);
  },

  view(vnode) {
    const { fsNode } = vnode.state;
    const canSubmit = canMoveHere(vnode);

    return m(
      Modal,
      vnode.attrs,
      m(".modal-dialog",
        m(".modal-content", [
          m(Modal.modalHeader, {
            title: fsNode ? `Move "${fsNode.name}"` : "Move",
            ...vnode.attrs,
          }),
          m("form.has-validation", {
            onsubmit: (event) => {
              event.preventDefault();
              if (canSubmit) {
                sendMoveFsNodeRequest(vnode);
              }
            },
          }, [
            m(".modal-body", [
              vnode.state.error && m(
                ".alert.alert-danger",
                getApiErrorDetail(vnode.state.error),
              ),
              fsNode && m("p", [
                "Choose a destination for ",
                m("strong", fsNode.name),
                ".",
              ]),
              renderBreadcrumbs(vnode),
              vnode.state.loading
                ? m(".text-muted", "Loading…")
                : renderDirectories(vnode),
            ]),
            renderFooter(vnode, canSubmit),
          ]),
        ]),
      ),
    );
  },
};

export {
  MoveFsNodeModal,
  canMoveHere,
  getBreadcrumbItems,
  getDirectories,
  loadDirectory,
  sendMoveFsNodeRequest,
};
