import m from "mithril";

/**
 * Download button for the directory that is currently being browsed.
 *
 * Directories are downloaded as ZIP archives, so the click is handed to the
 * caller which opens the archive waiting modal. The link is kept as a
 * no-JavaScript fallback to the server-rendered waiting page.
 */
export const FolderDownloadButton = {
  view(vnode) {
    const { fsNode, onDownload } = vnode.attrs;
    if (!fsNode || fsNode.type !== "directory" || !fsNode.download_url) {
      return null;
    }

    return m(
      "a.btn.btn-outline-primary.btn-sm",
      {
        href: m.buildPathname(fsNode.download_url, {
          disposition: "attachment",
        }),
        title: `Download ${fsNode.name} as ZIP`,
        onclick: (event) => {
          if (!onDownload) {
            return;
          }
          event.preventDefault();
          onDownload(fsNode);
        },
      },
      [
        m("span.fa.fa-download[aria-hidden=true]"),
        " Download folder",
      ],
    );
  },
};
