import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ShareFsNodeListService } from "../shareFsNodeList";

const file = {
  name: "file.txt",
  type: "file",
  path: "/file.txt",
};
const directory = {
  name: "docs",
  type: "directory",
  path: "/docs",
};
const child = {
  name: "notes.txt",
  type: "file",
  path: "/docs/notes.txt",
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
  });
});
