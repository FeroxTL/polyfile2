import { describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ShareFsNodeActionbarView } from "../ShareFsNodeActionbarView";

const renderActionbar = (selectedList, onClose = vi.fn()) => (
  ShareFsNodeActionbarView.view({
    attrs: {
      selectedList,
      onClose,
    },
  })
);

const getDownloadLink = (vnode) => vnode.children[1].children[0];
const getCloseLink = (vnode) => vnode.children[1].children[1];

describe("ShareFsNodeActionbarView", () => {
  it("enables download when the selected item has a download URL", () => {
    const selectedItem = {
      name: "file.txt",
      type: "file",
      download_url: "/api/shares/download/token/file/",
    };
    const downloadLink = getDownloadLink(renderActionbar([selectedItem]));

    expect(downloadLink.attrs.className).not.toContain("disabled");
    expect(downloadLink.attrs.href).toBe(m.buildPathname(selectedItem.download_url, {
      disposition: "attachment",
    }));
  });

  it("disables download when the selected item has no download URL", () => {
    const selectedItem = {
      name: "docs",
      type: "directory",
      download_url: "",
    };
    const downloadLink = getDownloadLink(renderActionbar([selectedItem]));

    expect(downloadLink.attrs.className).toContain("disabled");
  });

  it("clears the selection when the close button is clicked", () => {
    const onClose = vi.fn();
    const closeLink = getCloseLink(renderActionbar([
      {
        name: "file.txt",
        type: "file",
        download_url: "/api/shares/download/token/file/",
      },
    ], onClose));

    closeLink.attrs.onclick();

    expect(onClose).toHaveBeenCalledOnce();
  });
});
