import m from "mithril";

import { DashboardShell } from "../components/DashboardShell";
import { TrashList } from "../services/TrashList";
import { showTrashConfirmModal } from "../modals/trash_confirm_modal";
import { showRestoreMonitorModal } from "../modals/restore_monitor_modal";
import Button from "@polyfile/core/ui-kit/button";

const formatDate = (value) => {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
};

const renderEmpty = () => m(
  "li.list-group-item.text-center.text-muted.py-4",
  "Trash is empty.",
);

const renderEntry = (service, entry) => m(
  "li.list-group-item.list-group-item-action.py-2.d-flex.align-items-center",
  {
    key: entry.id,
    class: service.selected.has(entry.id) ? "active" : "",
    onclick: (event) => {
      event.preventDefault();
      // Keep the document-level "clear selection" handler from firing.
      event.stopPropagation();
      service.toggleSelected(entry.id);
    },
  },
  [
    m("span.fsnode-icon.me-2.flex-shrink-0",
      m("i.h5.mb-0.fa[aria-hidden=true]", {
        class: entry.type === "directory" ? "fa-folder" : "fa-file",
      }),
    ),
    m("span.flex-grow-1.text-truncate", { title: entry.name, style: "min-width: 0;" }, entry.name),
    m("span.text-nowrap.ms-2.d-none.d-sm-inline", formatDate(entry.trashed_at)),
  ],
);

const renderActionBar = (service, selected) => m(
  ".card.text-bg-dark.sticky-top.app-ignore-selection",
  m(".card-body.p-2.ps-3", [
    m("div.d-flex.justify-content-between.align-items-center", [
      m("span", selected.length === 1
        ? `Selected: ${selected[0].name}`
        : `Selected ${selected.length} items`),
      m(".d-flex.gap-2", [
        m(Button, {
          type: "button",
          class: "btn-sm btn-outline-light",
          onclick: () => {
            showRestoreMonitorModal({
              entries: selected,
              service,
              onDone: () => service.load().catch(() => null),
            });
            service.clearSelected();
          },
        }, [m("span.fa.fa-trash-restore[aria-hidden=true]"), " ", "Restore"]),
        m(Button, {
          type: "button",
          class: "btn-sm btn-outline-light",
          onclick: () => {
            showTrashConfirmModal({
              entries: selected,
              onConfirm: () => Promise.all(selected.map((entry) => (
                service.deletePermanent(entry.id)
              ))).then(() => service.load()),
            });
          },
        }, [m("span.fa.fa-trash[aria-hidden=true]"), " ", "Delete permanently"]),
        m(Button, {
          type: "button",
          class: "btn-sm btn-outline-light",
          title: "Clear selection",
          onclick: () => service.clearSelected(),
        }, m("span.fa.fa-close[aria-hidden=true]")),
      ]),
    ]),
  ]),
);

const renderHeader = (service) => m(
  ".d-flex.justify-content-between.align-items-center.mb-3",
  [
    m("h4.mb-0", "Trash"),
    // Nothing to empty: the action would be a no-op.
    service.entries.length > 0 && m(Button, {
      type: "button",
      class: "btn-outline-danger",
      onclick: () => {
        showTrashConfirmModal({
          title: "Empty trash",
          message: "Permanently delete every entry in the Trash?",
          confirmLabel: "Empty trash",
          entries: service.entries,
          onConfirm: () => service.empty().then(() => service.load()),
        });
      },
    }, [m("span.fa.fa-trash[aria-hidden=true]"), " ", "Empty trash"]),
  ],
);

const TrashDashboardView = {
  oninit(vnode) {
    vnode.state.service = TrashList;
    vnode.state.onDocumentClick = (event) => {
      // Clicking outside the list or the action bar clears the selection, mirroring the Files page behavior.
      if (!event.target.closest(".app-ignore-selection")) {
        TrashList.clearSelected();
        m.redraw();
      }
    };
    TrashList.load().catch(() => null);
  },

  oncreate(vnode) {
    document.addEventListener("click", vnode.state.onDocumentClick);
  },

  onremove(vnode) {
    document.removeEventListener("click", vnode.state.onDocumentClick);
  },

  view(vnode) {
    const { service } = vnode.state;
    const selected = service.getSelectedEntries();

    return m(DashboardShell, [
      m(".container-fluid.p-3.p-md-4", [
        selected.length > 0 ? renderActionBar(service, selected) : renderHeader(service),
        m("p.text-muted.small", "Items are kept in the Trash for 30 days, then deleted automatically."),
        service.isLoading && m(".text-muted", "Loading..."),
        service.error && m(".alert alert-danger", "Failed to load the Trash."),
        !service.isLoading && !service.error && m(
          "ul.list-group.user-select-none",
          service.entries.length
            ? service.entries.map((entry) => renderEntry(service, entry))
            : [renderEmpty()],
        ),
      ]),
    ]);
  },
};

export { TrashDashboardView };
