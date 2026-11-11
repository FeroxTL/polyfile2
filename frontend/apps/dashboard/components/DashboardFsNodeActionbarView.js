import m from "mithril";

const renderAction = ({
  title,
  icon,
  href,
  disabled = false,
  onClick,
}) => m(
  "a.btn.btn-outline-light.me-md-2",
  {
    class: disabled ? "disabled" : "",
    href,
    title,
    disabled,
    onclick: onClick,
  },
  [
    m(`span.fa.${icon}[aria-hidden=true]`),
    " ",
    m("span.d-lg-inline-block.d-none", title),
  ],
);

const renderDownloadAction = (selectedItem, onDownload) => {
  const canDownload = Boolean(selectedItem && selectedItem.download_url);
  const isDirectory = selectedItem?.type === "directory";

  return m(
    "a.btn.btn-outline-light.me-md-2",
    {
      class: canDownload ? "" : "disabled",
      href: m.buildPathname(selectedItem?.download_url || "#", {
        disposition: "attachment",
      }),
      title: "Download",
      onclick: (event) => {
        if (!canDownload) {
          event.preventDefault();
          return;
        }
        if (isDirectory && onDownload) {
          event.preventDefault();
          onDownload(selectedItem);
        }
      },
    },
    [
      m("span.fa.fa-download[aria-hidden=true]"),
      " ",
      m("span.d-lg-inline-block.d-none", "Download"),
    ],
  );
};

const renderSelection = (selectedList, selectedItem) => m(
  ".col.py-2.text-nowrap.overflow-hidden",
  m(
    "span",
    (selectedList.length === 1
      && m(
        "span",
        m(
          "i.h5.mb-0.fa.d-none.d-lg-inline",
          {
            class: selectedItem.type === "directory" ? "fa-folder" : "fa-file",
          },
        ),
        [" ", selectedItem.name],
      ))
    || `Selected ${selectedList.length} items`,
  ),
);

/**
 * Action bar shown while one or more dashboard nodes are selected.
 *
 * The download action is passed to the caller so this view stays free of
 * routing and modal concerns.
 */
export const DashboardFsNodeActionbarView = {
  view(vnode) {
    const {
      selectedList,
      onClose,
      onShare,
      onRemove,
      onDownload,
    } = vnode.attrs;
    const selectedItem = selectedList.length === 1 ? selectedList[0] : null;

    return m(".row.app-ignore-selection", [
      renderSelection(selectedList, selectedItem),
      m(".col.d-flex.justify-content-end.col-auto", [
        renderDownloadAction(selectedItem, onDownload),
        renderAction({
          title: "Share",
          icon: "fa-share",
          disabled: !selectedItem,
          onClick: (event) => {
            event.preventDefault();
            if (selectedItem && onShare) {
              onShare(selectedItem);
            }
          },
        }),
        renderAction({
          title: "Rename",
          icon: "fa-edit",
          disabled: true,
        }),
        renderAction({
          title: "Move",
          icon: "fa-arrow-right-arrow-left",
          disabled: true,
        }),
        renderAction({
          title: "Remove",
          icon: "fa-trash",
          onClick: () => {
            if (onRemove) {
              onRemove();
            }
          },
        }),
        m(
          "a.btn.btn-outline-light",
          {
            title: "Close",
            onclick: () => {
              if (onClose) {
                onClose();
              }
            },
          },
          m("span.fa.fa-close[aria-hidden=true]"),
        ),
      ]),
    ]);
  },
};
