import m from "mithril";

export const ShareFsNodeActionbarView = {
  view(vnode) {
    const { selectedList, onClose } = vnode.attrs;
    const selectedItem = selectedList.length === 1 ? selectedList[0] : null;
    const canDownload = Boolean(selectedItem && selectedItem.download_url);

    return m(".row app-ignore-selection", [
      m(".col py-2 text-nowrap overflow-hidden", m("span",
        selectedItem
          && m("span", [
            m("i.h5 mb-0 fa d-none d-lg-inline", {
              class: selectedItem.type === "directory" ? "fa-folder" : "fa-file",
            }),
            " ",
            selectedItem.name,
          ])
          || `Selected ${selectedList.length} items`
      )),
      m(".col d-flex justify-content-end col-auto", [
        m("a.btn btn-outline-light me-md-2", {
          class: canDownload ? "" : "disabled",
          href: m.buildPathname(selectedItem?.download_url || "#", {
            disposition: "attachment",
          }),
          title: "Download",
        }, [
          m("span.fa fa-download[aria-hidden=true]"),
          " ",
          m("span.d-lg-inline-block d-none", "Download"),
        ]),
        m("a.btn btn-outline-light", {
          title: "Close",
          onclick: onClose,
        }, m("span.fa fa-close[aria-hidden=true]")),
      ]),
    ]);
  },
};
