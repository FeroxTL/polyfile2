import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ShareFsNodeListService } from "../shareFsNodeList";

const file = {
  name: "file.txt",
  type: "file",
  parent_id: null,
};
const directory = {
  name: "docs",
  type: "directory",
  parent_id: null,
};
const child = {
  name: "notes.txt",
  type: "file",
  parent_id: "33333333-3333-3333-3333-333333333333",
};

describe("ShareFsNodeListService.load()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("exposes a shared file as the only list item", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: file,
      children: [],
    });
    const service = new ShareFsNodeListService();

    await service.load("/api/shares/detail/token/");

    expect(service.elements).toHaveLength(1);
    expect(service.elements[0].name).toBe(file.name);
    expect(service.elements[0].type).toBe("file");
    // The shared file renders as the share root itself.
    expect(service.path).toBe("/");
  });

  it("keeps rendering directory children as list items", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: directory,
      children: [child],
    });
    const service = new ShareFsNodeListService();

    await service.load("/api/shares/detail/token/");

    expect(service.elements).toHaveLength(1);
    expect(service.elements[0].name).toBe(child.name);
    expect(service.path).toBe("/");
  });
});
