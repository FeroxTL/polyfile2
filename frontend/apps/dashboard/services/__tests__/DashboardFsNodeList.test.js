import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { DashboardFsNode } from "../../models/DashboardFsNode";
import { DashboardFsNodeListService } from "../DashboardFsNodeList";

const NODE_ID = "11111111-1111-1111-1111-111111111111";

const createService = () => {
  const service = new DashboardFsNodeListService();
  service.current = { id: "22222222-2222-2222-2222-222222222222" };
  return service;
};

describe("DashboardFsNodeListService.createShare()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a share by node id and updates the node in place", async () => {
    const shareResponse = {
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: null,
    };
    const request = vi.spyOn(m, "request").mockResolvedValue(shareResponse);
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "report #1.txt" });

    const data = await service.createShare(fsNode);

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      body: { node_id: NODE_ID },
      method: "POST",
    });
    expect(data.id).toBe("token");
    expect(fsNode.share).toEqual({
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: null,
    });
    expect(fsNode.is_shared).toBe(true);
  });

  it("posts an expiration and stores it on the node", async () => {
    const expiresAt = "2030-01-02T03:04:00.000Z";
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: expiresAt,
    });
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "file.txt" });

    await service.createShare(fsNode, expiresAt);

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      method: "POST",
      body: { node_id: NODE_ID, expires_at: expiresAt },
    });
    expect(fsNode.share).toEqual({
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: expiresAt,
    });
  });

  it("sends null to clear an existing expiration", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: null,
    });
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "file.txt" });

    await service.createShare(fsNode, null);

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      method: "POST",
      body: { node_id: NODE_ID, expires_at: null },
    });
  });

  it("does not mark the node as shared when the request fails", async () => {
    vi.spyOn(m, "request").mockRejectedValue(new Error("network error"));
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "file.txt" });

    await expect(service.createShare(fsNode)).rejects.toThrow("network error");
    expect(fsNode.share).toBeNull();
    expect(fsNode.is_shared).toBe(false);
  });
});

describe("DashboardFsNodeListService.revokeShare()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("deletes the share by token and clears the node state", async () => {
    const share = {
      id: "4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10",
      url: "https://example.com/s/4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10/",
    };
    const request = vi.spyOn(m, "request").mockResolvedValue();
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "report.txt", share });

    await service.revokeShare(fsNode);

    expect(request).toHaveBeenCalledWith(`/api/shares/${share.id}/revoke`, {
      method: "POST",
    });
    expect(fsNode.share).toBeNull();
    expect(fsNode.is_shared).toBe(false);
  });

  it("does nothing when the node has no active share", async () => {
    const request = vi.spyOn(m, "request");
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "file.txt" });

    await service.revokeShare(fsNode);

    expect(request).not.toHaveBeenCalled();
    expect(fsNode.share).toBeNull();
  });

  it("keeps the share when the revoke request fails", async () => {
    const share = {
      id: "4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10",
      url: "https://example.com/s/4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10/",
    };
    vi.spyOn(m, "request").mockRejectedValue(new Error("network error"));
    const service = createService();
    const fsNode = new DashboardFsNode({ id: NODE_ID, name: "file.txt", share });

    await expect(service.revokeShare(fsNode)).rejects.toThrow("network error");
    expect(fsNode.share).toEqual(share);
    expect(fsNode.is_shared).toBe(true);
  });
});

describe("DashboardFsNodeListService UUID preload", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads by UUID and consumes the matching route path once", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      current: { id: NODE_ID, parent_id: null, name: "docs", type: "directory" },
      ancestors: [],
      children: [],
    });
    const service = new DashboardFsNodeListService();

    await service.loadByNodeId(NODE_ID, "docs/");

    expect(request).toHaveBeenCalledWith(
      `/api/v1/fs-node/${NODE_ID}/`,
      expect.objectContaining({ method: "GET" }),
    );
    expect(service.consumePendingPath("/docs")).toBe(true);
    expect(service.consumePendingPath("/docs")).toBe(false);
  });

  it("does not skip a different route path", () => {
    const service = new DashboardFsNodeListService();
    service.pendingPath = "/docs";

    expect(service.consumePendingPath("/other")).toBe(false);
    // The marker is consumed even on a mismatch to avoid stale skips.
    expect(service.consumePendingPath("/docs")).toBe(false);
  });

  it("loads by UUID without a pending path when the path is not known yet", async () => {
    vi.spyOn(m, "request").mockResolvedValue({
      current: { id: NODE_ID, parent_id: null, name: "docs", type: "directory" },
      ancestors: [],
      children: [],
    });
    const service = new DashboardFsNodeListService();

    await service.loadByNodeId(NODE_ID);

    expect(service.path).toBe("/docs");
    expect(service.consumePendingPath("/docs")).toBe(false);
  });

  it("marks an already loaded path for the next route match", () => {
    const service = new DashboardFsNodeListService();

    service.markPathPending("docs/");

    expect(service.consumePendingPath("/docs")).toBe(true);
  });
});
