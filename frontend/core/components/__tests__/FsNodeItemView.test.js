// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";

import FsNodeItemView from "../FsNodeItemView";

describe("FsNodeItemView.navigate()", () => {
  it("passes the target node to the navigation handler for directories", () => {
    const fsnodeList = { path: "/docs", elements: [] };
    const fsNode = { name: "sub", type: "directory" };
    const navigationHandler = vi.fn();
    const event = { preventDefault: vi.fn() };

    FsNodeItemView.navigate(fsNode, event, fsnodeList, navigationHandler);

    expect(navigationHandler).toHaveBeenCalledWith("/docs", "sub", fsNode);
    expect(event.preventDefault).toHaveBeenCalled();
  });
});
