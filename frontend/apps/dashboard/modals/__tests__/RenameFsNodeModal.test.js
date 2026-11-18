import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";
import stream from "mithril/stream";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { closeModal } from "../../bootstrap/modal";
import { DashboardFsNode } from "../../models/DashboardFsNode";
import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import {
  RenameFsNodeModal,
  sendRenameFsNodeRequest,
} from "../RenameFsNodeModal";

const NODE_ID = "11111111-1111-1111-1111-111111111111";

const makeNode = (name = "old.txt") => new DashboardFsNode({
  id: NODE_ID,
  name,
});

const createVnode = (fsNode, name = "new.txt") => ({
  attrs: { modalId: ["modal"], fsNode },
  state: {
    fsNode,
    valueStream: stream(name),
    fieldErrors: [],
    error: null,
  },
});

describe("RenameFsNodeModal", () => {
  beforeEach(() => {
    DashboardFsNodeList.current = { id: "22222222-2222-2222-2222-222222222222" };
    DashboardFsNodeList.elements = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
  });

  it("prefills the current node name", () => {
    const fsNode = makeNode("report.txt");
    const vnode = { attrs: { fsNode }, state: {} };

    RenameFsNodeModal.oninit(vnode);

    expect(vnode.state.valueStream()).toBe("report.txt");
    expect(vnode.state.fieldErrors).toEqual([]);
  });
});

describe("sendRenameFsNodeRequest()", () => {
  beforeEach(() => {
    DashboardFsNodeList.current = { id: "22222222-2222-2222-2222-222222222222" };
    DashboardFsNodeList.elements = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
  });

  it("renames the node by UUID and closes the modal", async () => {
    const fsNode = makeNode();
    DashboardFsNodeList.elements = [fsNode];
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: NODE_ID,
      name: "new.txt",
      modified_at: "2026-02-01T00:00:00Z",
    });
    const vnode = createVnode(fsNode, "new.txt");

    await sendRenameFsNodeRequest(vnode);

    expect(request).toHaveBeenCalledWith(`/api/v1/fs-node/${NODE_ID}/`, {
      method: "PATCH",
      body: { name: "new.txt" },
    });
    expect(fsNode.name).toBe("new.txt");
    expect(closeModal).toHaveBeenCalledWith(vnode.attrs.modalId);
  });

  it("shows a conflict message and keeps the modal open", async () => {
    const fsNode = makeNode();
    vi.spyOn(m, "request").mockRejectedValue({
      code: 409,
      response: { detail: 'File named "taken.txt" already exists' },
    });
    const vnode = createVnode(fsNode, "taken.txt");

    await sendRenameFsNodeRequest(vnode);

    expect(vnode.state.fieldErrors).toEqual([
      'File named "taken.txt" already exists',
    ]);
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("unwraps object-shaped validation details", async () => {
    const fsNode = makeNode();
    vi.spyOn(m, "request").mockRejectedValue({
      code: 400,
      response: {
        detail: {
          name: ["Name contains reserved characters"],
        },
      },
    });
    const vnode = createVnode(fsNode, "valid.txt");

    await sendRenameFsNodeRequest(vnode);

    expect(vnode.state.fieldErrors).toEqual([
      "Name contains reserved characters",
    ]);
    expect(vnode.state.fieldErrors[0]).not.toContain("[object Object]");
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("does not send a request for an unchanged name", async () => {
    const fsNode = makeNode("old.txt");
    const request = vi.spyOn(m, "request");
    const vnode = createVnode(fsNode, "old.txt");

    await sendRenameFsNodeRequest(vnode);

    expect(request).not.toHaveBeenCalled();
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("does not send an invalid name", async () => {
    const fsNode = makeNode();
    const request = vi.spyOn(m, "request");
    const vnode = createVnode(fsNode, "a/b");

    await sendRenameFsNodeRequest(vnode);

    expect(request).not.toHaveBeenCalled();
    expect(vnode.state.fieldErrors.length).toBe(1);
    expect(closeModal).not.toHaveBeenCalled();
  });
});
