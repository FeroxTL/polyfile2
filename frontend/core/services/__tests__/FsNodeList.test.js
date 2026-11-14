import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { FsNodeList } from "../FsNodeList";

describe("FsNodeList.load()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("stores the ancestors from the response", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: {
        id: "22222222-2222-2222-2222-222222222222",
        parent_id: "11111111-1111-1111-1111-111111111111",
        name: "sub",
        type: "directory",
      },
      ancestors: [{ id: "11111111-1111-1111-1111-111111111111", name: "root" }],
      children: [],
    });
    const list = new FsNodeList();

    await list.load("/api/v1/fs-node/", { path: "/root/sub" });

    expect(list.current.id).toBe("22222222-2222-2222-2222-222222222222");
    expect(list.ancestors).toEqual([
      { id: "11111111-1111-1111-1111-111111111111", name: "root" },
    ]);
  });

  it("defaults ancestors to an empty list when the key is absent", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: { id: null, parent_id: null, name: "", type: "directory" },
      children: [],
    });
    const list = new FsNodeList();

    await list.load("/api/v1/fs-node/", { path: "/" });

    expect(list.ancestors).toEqual([]);
  });

  it("derives the current path from ancestors and name", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: {
        id: "22222222-2222-2222-2222-222222222222",
        parent_id: "11111111-1111-1111-1111-111111111111",
        name: "sub",
        type: "directory",
      },
      ancestors: [{ id: "11111111-1111-1111-1111-111111111111", name: "root" }],
      children: [],
    });
    const list = new FsNodeList();

    await list.load("/api/v1/fs-node/", { path: "/root/sub" });

    expect(list.path).toBe("/root/sub");
    expect(list.pathSegments).toEqual(["root", "sub"]);
    expect(list.breadcrumbNodes.map((node) => node.id)).toEqual([
      "11111111-1111-1111-1111-111111111111",
      "22222222-2222-2222-2222-222222222222",
    ]);
    // The path is derived for the list, it is not part of the node itself.
    expect(list.current.path).toBeUndefined();
  });

  it("derives '/' for the virtual root", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: { id: null, parent_id: null, name: "", type: "directory" },
      ancestors: [],
      children: [],
    });
    const list = new FsNodeList();

    await list.load("/api/v1/fs-node/", { path: "/" });

    expect(list.path).toBe("/");
    expect(list.pathSegments).toEqual([]);
    expect(list.breadcrumbNodes).toEqual([]);
  });

  it("derives '/' for the masked share root", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: { id: "33333333-3333-3333-3333-333333333333", parent_id: null, name: "shared", type: "directory" },
      ancestors: [],
      children: [],
    });
    const list = new FsNodeList();
    list.stripShareRoot = true;

    await list.load("/api/shares/detail/token/", {});

    expect(list.path).toBe("/");
    expect(list.pathSegments).toEqual([]);
    expect(list.breadcrumbNodes).toEqual([]);
  });

  it("hides the share root name in nested paths", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: {
        id: "22222222-2222-2222-2222-222222222222",
        parent_id: "33333333-3333-3333-3333-333333333333",
        name: "sub",
        type: "directory",
      },
      ancestors: [{ id: "33333333-3333-3333-3333-333333333333", name: "shared" }],
      children: [],
    });
    const list = new FsNodeList();
    list.stripShareRoot = true;

    await list.load("/api/shares/detail/token/", {});

    expect(list.path).toBe("/sub");
    expect(list.pathSegments).toEqual(["sub"]);
  });
});
