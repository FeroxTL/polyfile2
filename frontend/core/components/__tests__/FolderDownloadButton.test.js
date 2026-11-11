import { describe, expect, it, vi } from "vitest";
import m from "mithril";

import { FolderDownloadButton } from "../FolderDownloadButton";

const renderButton = (attrs) => FolderDownloadButton.view({ attrs });

describe("FolderDownloadButton", () => {
  it("renders nothing for files", () => {
    const button = renderButton({
      fsNode: { name: "file.txt", type: "file", download_url: "/download/file/" },
      onDownload: vi.fn(),
    });

    expect(button).toBeNull();
  });

  it("renders nothing without a download URL", () => {
    const button = renderButton({
      fsNode: { name: "docs", type: "directory", download_url: "" },
      onDownload: vi.fn(),
    });

    expect(button).toBeNull();
  });

  it("links to the archive download URL", () => {
    const fsNode = {
      name: "docs",
      type: "directory",
      download_url: "/download/node/",
    };
    const button = renderButton({ fsNode, onDownload: vi.fn() });

    expect(button.attrs.href).toBe(m.buildPathname(
      fsNode.download_url,
      { disposition: "attachment" },
    ));
  });

  it("opens the archive modal on click", () => {
    const fsNode = {
      name: "docs",
      type: "directory",
      download_url: "/download/node/",
    };
    const onDownload = vi.fn();
    const button = renderButton({ fsNode, onDownload });
    const event = { preventDefault: vi.fn() };

    button.attrs.onclick(event);

    expect(onDownload).toHaveBeenCalledWith(fsNode);
    expect(event.preventDefault).toHaveBeenCalled();
  });
});
