import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { DashboardFsNode } from "../../models/DashboardFsNode";
import { DashboardFsNodeListService } from "../DashboardFsNodeList";

const NODE_ID = "11111111-1111-1111-1111-111111111111";
const CURRENT_ID = "22222222-2222-2222-2222-222222222222";
const DESTINATION_ID = "44444444-4444-4444-4444-444444444444";

const createNode = (overrides = {}) => {
  const node = new DashboardFsNode({
    id: NODE_ID,
    parent_id: CURRENT_ID,
    name: "file.txt",
    type: "file",
    ...overrides,
  });
  node.selected = true;
  return node;
};

const createService = (elements) => {
  const service = new DashboardFsNodeListService();
  service.current = { id: CURRENT_ID };
  service.elements = elements;
  return service;
};

const expectedRequest = (parentId) => [
  `/api/v1/fs-node/${NODE_ID}/`,
  { method: "PATCH", body: { parent_id: parentId } },
];

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DashboardFsNodeListService.moveFsNode() success", () => {
  it("moves by UUID and removes the node from the listing", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: NODE_ID,
      parent_id: DESTINATION_ID,
      name: "file.txt",
    });
    const node = createNode();
    const other = createNode({ id: CURRENT_ID, name: "other.txt" });
    const service = createService([other, node]);

    const data = await service.moveFsNode(node, DESTINATION_ID);

    expect(request).toHaveBeenCalledWith(...expectedRequest(DESTINATION_ID));
    expect(data.parent_id).toBe(DESTINATION_ID);
    expect(node.parent_id).toBe(DESTINATION_ID);
    expect(node.selected).toBe(false);
    expect(service.elements).toEqual([other]);
  });

  it("sends null to move a node to the virtual root", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: NODE_ID,
      parent_id: null,
      name: "file.txt",
    });
    const node = createNode();
    const service = createService([node]);

    await service.moveFsNode(node, null);

    expect(request).toHaveBeenCalledWith(...expectedRequest(null));
    expect(node.parent_id).toBeNull();
    expect(node.selected).toBe(false);
    expect(service.elements).toEqual([]);
  });
});

describe("DashboardFsNodeListService.moveFsNode() edge cases", () => {
  it("keeps the node listed when the destination is its current parent", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      id: NODE_ID,
      parent_id: CURRENT_ID,
      name: "file.txt",
    });
    const node = createNode();
    const service = createService([node]);

    await service.moveFsNode(node, CURRENT_ID);

    expect(node.selected).toBe(true);
    expect(service.elements).toEqual([node]);
  });

  it("keeps the node state when the request fails", async () => {
    vi.spyOn(m, "request").mockRejectedValue(new Error("network error"));
    const node = createNode();
    const service = createService([node]);

    await expect(service.moveFsNode(node, DESTINATION_ID))
      .rejects.toThrow("network error");
    expect(node.parent_id).toBe(CURRENT_ID);
    expect(node.selected).toBe(true);
    expect(service.elements).toEqual([node]);
  });
});
