import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { closeModal } from "../../bootstrap/modal";
import { DashboardFsNode } from "../../models/DashboardFsNode";
import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import { sendRemoveFsNodesRequest } from "../RemoveFsNodeModal";

const NODE_A = "11111111-1111-1111-1111-111111111111";
const NODE_B = "22222222-2222-2222-2222-222222222222";

const createVnode = (removeList, permanent = false) => ({
  attrs: { modalId: ["modal"] },
  state: { removeList, error: null, permanent },
});

describe("sendRemoveFsNodesRequest()", () => {
  beforeEach(() => {
    DashboardFsNodeList.elements = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
  });

  it("deletes every selected node by its UUID", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});
    const vnode = createVnode([
      new DashboardFsNode({ id: NODE_A, name: "a.txt" }),
      new DashboardFsNode({ id: NODE_B, name: "b.txt" }),
    ]);

    await sendRemoveFsNodesRequest(vnode);

    expect(request).toHaveBeenCalledTimes(2);
    expect(request).toHaveBeenCalledWith(`/api/v1/fs-node/${NODE_A}/`, { method: "DELETE" });
    expect(request).toHaveBeenCalledWith(`/api/v1/fs-node/${NODE_B}/`, { method: "DELETE" });
    expect(closeModal).toHaveBeenCalledWith(vnode.attrs.modalId);
  });

  it("removes the deleted nodes from the list", async () => {
    vi.spyOn(m, "request").mockResolvedValue({});
    const nodeA = new DashboardFsNode({ id: NODE_A, name: "a.txt" });
    const nodeB = new DashboardFsNode({ id: NODE_B, name: "b.txt" });
    const kept = new DashboardFsNode({ id: "33333333-3333-3333-3333-333333333333", name: "c.txt" });
    DashboardFsNodeList.elements = [nodeA, nodeB, kept];

    await sendRemoveFsNodesRequest(createVnode([nodeA]));

    expect(DashboardFsNodeList.elements).toEqual([nodeB, kept]);
  });

  it("does nothing when nothing is selected", async () => {
    const request = vi.spyOn(m, "request");

    await sendRemoveFsNodesRequest(createVnode([]));

    expect(request).not.toHaveBeenCalled();
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("shows the error when a delete request fails", async () => {
    const error = { code: 404, response: { detail: "Not found." } };
    vi.spyOn(m, "request").mockRejectedValue(error);
    const vnode = createVnode([new DashboardFsNode({ id: NODE_A, name: "a.txt" })]);

    await sendRemoveFsNodesRequest(vnode);

    expect(vnode.state.error).toBe(error);
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("moves nodes to the Trash by default", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});
    const vnode = createVnode([new DashboardFsNode({ id: NODE_A, name: "a.txt" })]);

    await sendRemoveFsNodesRequest(vnode);

    expect(request).toHaveBeenCalledWith(`/api/v1/fs-node/${NODE_A}/`, { method: "DELETE" });
  });

  it("deletes permanently when the bypass flag is set", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});
    const vnode = createVnode([new DashboardFsNode({ id: NODE_A, name: "a.txt" })], true);

    await sendRemoveFsNodesRequest(vnode);

    expect(request).toHaveBeenCalledWith(`/api/v1/fs-node/${NODE_A}/`, {
      method: "DELETE",
      params: { permanent: "true" },
    });
  });
});
