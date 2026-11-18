import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { FsNodeList } from "@polyfile/core/services/FsNodeList";
import { closeModal } from "../../bootstrap/modal";
import { DashboardFsNode } from "../../models/DashboardFsNode";
import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import {
  MoveFsNodeModal,
  canMoveHere,
  getBreadcrumbItems,
  getDirectories,
  loadDirectory,
  sendMoveFsNodeRequest,
} from "../MoveFsNodeModal";

const NODE_ID = "11111111-1111-1111-1111-111111111111";
const CURRENT_ID = "22222222-2222-2222-2222-222222222222";
const TARGET_ID = "44444444-4444-4444-4444-444444444444";

const makeNode = (overrides = {}) => new DashboardFsNode({
  id: NODE_ID,
  parent_id: CURRENT_ID,
  name: "file.txt",
  type: "file",
  ...overrides,
});

const makeList = (overrides = {}) => {
  const list = new FsNodeList(DashboardFsNode);
  Object.assign(list, overrides);
  return list;
};

const createVnode = (fsNode = makeNode(), fsNodeList = makeList({
  current: { id: TARGET_ID, name: "target" },
})) => ({
  attrs: { modalId: ["modal"], fsNode },
  state: {
    fsNode,
    fsNodeList,
    loading: false,
    error: null,
  },
});

beforeEach(() => {
  DashboardFsNodeList.current = { id: CURRENT_ID };
  DashboardFsNodeList.elements = [];
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(closeModal).mockClear();
});

describe("MoveFsNodeModal.oninit()", () => {
  it("uses the passed node and loads the virtual root", async () => {
    const load = vi.spyOn(FsNodeList.prototype, "load").mockResolvedValue();
    const fsNode = makeNode();
    const vnode = { attrs: { fsNode }, state: {} };

    MoveFsNodeModal.oninit(vnode);

    expect(vnode.state.fsNode).toBe(fsNode);
    expect(vnode.state.fsNodeList).toBeInstanceOf(FsNodeList);
    expect(load).toHaveBeenCalledWith("/api/v1/fs-node/", { path: "/" });
    await vi.waitFor(() => expect(vnode.state.loading).toBe(false));
  });

  it("falls back to the selected dashboard node", async () => {
    vi.spyOn(FsNodeList.prototype, "load").mockResolvedValue();
    const fsNode = makeNode();
    fsNode.selected = true;
    DashboardFsNodeList.elements = [fsNode];
    const vnode = { attrs: {}, state: {} };

    MoveFsNodeModal.oninit(vnode);

    expect(vnode.state.fsNode).toBe(fsNode);
    await vi.waitFor(() => expect(vnode.state.loading).toBe(false));
  });
});

describe("loadDirectory()", () => {
  it("loads the virtual root", async () => {
    const load = vi.spyOn(FsNodeList.prototype, "load").mockResolvedValue();
    const vnode = createVnode();

    const request = loadDirectory(vnode, null);
    expect(vnode.state.loading).toBe(true);

    await request;

    expect(load).toHaveBeenCalledWith("/api/v1/fs-node/", { path: "/" });
    expect(vnode.state.loading).toBe(false);
    expect(vnode.state.error).toBeNull();
  });

  it("loads a directory by UUID", async () => {
    const load = vi.spyOn(FsNodeList.prototype, "load").mockResolvedValue();
    const vnode = createVnode();

    await loadDirectory(vnode, TARGET_ID);

    expect(load).toHaveBeenCalledWith(
      `/api/v1/fs-node/${TARGET_ID}/`,
      {},
    );
  });

  it("surfaces the list error", async () => {
    const error = { code: 404 };
    const vnode = createVnode();
    vi.spyOn(FsNodeList.prototype, "load").mockImplementation(() => {
      vnode.state.fsNodeList.error = error;
      return Promise.resolve();
    });

    await loadDirectory(vnode, null);

    expect(vnode.state.error).toBe(error);
    expect(vnode.state.loading).toBe(false);
  });
});

describe("getDirectories()", () => {
  it("keeps only directory children", () => {
    const list = makeList({
      elements: [
        { id: "1", name: "docs", type: "directory" },
        { id: "2", name: "file.txt", type: "file" },
        { id: "3", name: "photos", type: "directory" },
      ],
    });

    expect(getDirectories(list).map((node) => node.name)).toEqual([
      "docs",
      "photos",
    ]);
  });
});

describe("getBreadcrumbItems()", () => {
  it("marks the virtual root active at the root", () => {
    const list = makeList({
      current: { id: null, name: "" },
      ancestors: [],
    });

    expect(getBreadcrumbItems(list)).toEqual([
      { id: null, name: "Files", active: true },
    ]);
  });

  it("lists ancestors and marks the current directory active", () => {
    const list = makeList({
      current: { id: TARGET_ID, name: "sub" },
      ancestors: [{ id: CURRENT_ID, name: "root" }],
    });

    expect(getBreadcrumbItems(list)).toEqual([
      { id: null, name: "Files", active: false },
      { id: CURRENT_ID, name: "root", active: false },
      { id: TARGET_ID, name: "sub", active: true },
    ]);
  });

  it("keeps the current directory active when it is repeated in ancestors", () => {
    const list = makeList({
      current: { id: TARGET_ID, name: "sub" },
      ancestors: [
        { id: CURRENT_ID, name: "root" },
        { id: TARGET_ID, name: "sub" },
      ],
    });

    expect(getBreadcrumbItems(list)).toEqual([
      { id: null, name: "Files", active: false },
      { id: CURRENT_ID, name: "root", active: false },
      { id: TARGET_ID, name: "sub", active: true },
    ]);
  });
});

describe("canMoveHere()", () => {
  it("requires a loaded destination that differs from the parent", () => {
    const vnode = createVnode();

    expect(canMoveHere(vnode)).toBe(true);
  });

  it("rejects the current parent", () => {
    const vnode = createVnode(makeNode({ parent_id: TARGET_ID }));

    expect(canMoveHere(vnode)).toBe(false);
  });

  it("rejects moving a directory into itself", () => {
    const fsNode = makeNode({ id: TARGET_ID, type: "directory" });
    const vnode = createVnode(fsNode, makeList({
      current: { id: TARGET_ID, name: "target" },
    }));

    expect(canMoveHere(vnode)).toBe(false);
  });

  it("rejects while loading or without a loaded destination", () => {
    const loadingVnode = createVnode();
    loadingVnode.state.loading = true;
    const emptyVnode = createVnode(makeNode(), makeList());

    expect(canMoveHere(loadingVnode)).toBe(false);
    expect(canMoveHere(emptyVnode)).toBe(false);
  });
});

describe("sendMoveFsNodeRequest()", () => {
  it("moves the node and closes the modal", async () => {
    const fsNode = makeNode();
    const move = vi.spyOn(DashboardFsNodeList, "moveFsNode")
      .mockResolvedValue({ parent_id: TARGET_ID });
    const vnode = createVnode(fsNode);

    await sendMoveFsNodeRequest(vnode);

    expect(move).toHaveBeenCalledWith(fsNode, TARGET_ID);
    expect(closeModal).toHaveBeenCalledWith(vnode.attrs.modalId);
    expect(vnode.state.error).toBeNull();
  });

  it("keeps the modal open and shows the API error", async () => {
    const error = { code: 409, response: { detail: "Name already exists" } };
    vi.spyOn(DashboardFsNodeList, "moveFsNode").mockRejectedValue(error);
    const vnode = createVnode();

    await sendMoveFsNodeRequest(vnode);

    expect(vnode.state.error).toBe(error);
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("does nothing for a no-op destination", async () => {
    const move = vi.spyOn(DashboardFsNodeList, "moveFsNode");
    const vnode = createVnode(makeNode({ parent_id: TARGET_ID }));

    await sendMoveFsNodeRequest(vnode);

    expect(move).not.toHaveBeenCalled();
    expect(closeModal).not.toHaveBeenCalled();
  });
});
