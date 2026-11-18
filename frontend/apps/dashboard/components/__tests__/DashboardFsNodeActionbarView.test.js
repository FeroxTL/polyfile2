import { describe, expect, it, vi } from "vitest";
import m from "mithril";

import { DashboardFsNodeActionbarView } from "../DashboardFsNodeActionbarView";

const renderActionbar = (selectedList, handlers = {}) => (
  DashboardFsNodeActionbarView.view({
    attrs: {
      selectedList,
      onClose: vi.fn(),
      onShare: vi.fn(),
      onRemove: vi.fn(),
      onDownload: vi.fn(),
      ...handlers,
    },
  })
);

const getActions = (vnode) => vnode.children[1].children;
const getDownloadLink = (vnode) => getActions(vnode)[0];

describe("DashboardFsNodeActionbarView", () => {
  it("disables download without a selected item", () => {
    const downloadLink = getDownloadLink(renderActionbar([]));

    expect(downloadLink.attrs.className).toContain("disabled");
  });

  it("links files directly to their download URL", () => {
    const selectedItem = {
      name: "file.txt",
      type: "file",
      download_url: "/download/file/",
    };
    const onDownload = vi.fn();
    const downloadLink = getDownloadLink(renderActionbar(
      [selectedItem],
      { onDownload },
    ));
    const event = { preventDefault: vi.fn() };

    downloadLink.attrs.onclick(event);

    expect(downloadLink.attrs.href).toBe(m.buildPathname(
      selectedItem.download_url,
      { disposition: "attachment" },
    ));
    expect(onDownload).not.toHaveBeenCalled();
    expect(event.preventDefault).not.toHaveBeenCalled();
  });

  it("opens the archive modal for directories", () => {
    const selectedItem = {
      name: "docs",
      type: "directory",
      download_url: "/download/node/",
    };
    const onDownload = vi.fn();
    const downloadLink = getDownloadLink(renderActionbar(
      [selectedItem],
      { onDownload },
    ));
    const event = { preventDefault: vi.fn() };

    downloadLink.attrs.onclick(event);

    expect(onDownload).toHaveBeenCalledWith(selectedItem);
    expect(event.preventDefault).toHaveBeenCalled();
  });

  it("opens the share modal for the selected item", () => {
    const selectedItem = {
      name: "file.txt",
      type: "file",
      download_url: "/download/file/",
    };
    const onShare = vi.fn();
    const [, shareLink] = getActions(renderActionbar([selectedItem], { onShare }));

    shareLink.attrs.onclick({ preventDefault: vi.fn() });

    expect(onShare).toHaveBeenCalledWith(selectedItem);
  });

  it("opens the rename modal for the selected item", () => {
    const selectedItem = {
      name: "file.txt",
      type: "file",
      download_url: "/download/file/",
    };
    const onRename = vi.fn();
    const [, , renameLink] = getActions(renderActionbar([selectedItem], { onRename }));

    expect(renameLink.attrs.className).not.toContain("disabled");

    renameLink.attrs.onclick({ preventDefault: vi.fn() });

    expect(onRename).toHaveBeenCalledWith(selectedItem);
  });

  it("disables rename when several items are selected", () => {
    const [, , renameLink] = getActions(renderActionbar([
      { name: "a.txt", type: "file", download_url: "/download/a/" },
      { name: "b.txt", type: "file", download_url: "/download/b/" },
    ]));

    expect(renameLink.attrs.className).toContain("disabled");
  });

  it("opens the move modal for the selected item", () => {
    const selectedItem = {
      name: "file.txt",
      type: "file",
      download_url: "/download/file/",
    };
    const onMove = vi.fn();
    const [, , , moveLink] = getActions(renderActionbar([selectedItem], { onMove }));

    expect(moveLink.attrs.className).not.toContain("disabled");

    moveLink.attrs.onclick({ preventDefault: vi.fn() });

    expect(onMove).toHaveBeenCalledWith(selectedItem);
  });

  it("disables move when several items are selected", () => {
    const [, , , moveLink] = getActions(renderActionbar([
      { name: "a.txt", type: "file", download_url: "/download/a/" },
      { name: "b.txt", type: "file", download_url: "/download/b/" },
    ]));

    expect(moveLink.attrs.className).toContain("disabled");
  });

  it("clears the selection from the close button", () => {
    const onClose = vi.fn();
    const actions = getActions(renderActionbar([
      { name: "file.txt", type: "file", download_url: "/download/file/" },
    ], { onClose }));

    actions[5].attrs.onclick();

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("opens the remove modal", () => {
    const onRemove = vi.fn();
    const actions = getActions(renderActionbar([
      { name: "file.txt", type: "file", download_url: "/download/file/" },
    ], { onRemove }));

    actions[4].attrs.onclick();

    expect(onRemove).toHaveBeenCalledOnce();
  });
});
