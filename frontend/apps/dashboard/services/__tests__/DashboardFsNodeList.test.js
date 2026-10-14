import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { DashboardFsNode } from "../../models/DashboardFsNode";
import { DashboardFsNodeListService } from "../DashboardFsNodeList";

const createService = (path = "/docs") => {
  const service = new DashboardFsNodeListService();
  service.current = { path };
  return service;
};

describe("DashboardFsNodeListService.createShare()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("encodes the target path and updates the node in place", async () => {
    const share = {
      id: "token",
      url: "https://example.com/s/token/",
    };
    const request = vi.spyOn(m, "request").mockResolvedValue({ share });
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "report #1.txt" });

    const data = await service.createShare(fsNode);

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/report%20%231.txt", {
      "body": {},
      method: "POST",
    });
    expect(data.share).toEqual(share);
    expect(fsNode.share).toEqual({ ...share, expires_at: null });
    expect(fsNode.is_shared).toBe(true);
  });

  it("posts an expiration and stores it on the node", async () => {
    const share = {
      id: "token",
      url: "https://example.com/s/token/",
    };
    const expiresAt = "2030-01-02T03:04:00.000Z";
    const request = vi.spyOn(m, "request").mockResolvedValue({ share, expires_at: expiresAt });
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "file.txt" });

    await service.createShare(fsNode, "/docs/file.txt", expiresAt);

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/file.txt", {
      method: "POST",
      body: { expires_at: expiresAt },
    });
    expect(fsNode.share).toEqual({ ...share, expires_at: expiresAt });
  });

  it("sends null to clear an existing expiration", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      share: { id: "token", url: "https://example.com/s/token/" },
      expires_at: null,
    });
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "file.txt" });

    await service.createShare(fsNode, "/docs/file.txt", null);

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/file.txt", {
      method: "POST",
      body: { expires_at: null },
    });
  });

  it("uses an explicit path when provided", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      share: { id: "token", url: "https://example.com/s/token/" },
    });
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "file.txt" });

    await service.createShare(fsNode, "/other/nested/file.txt");

    expect(request).toHaveBeenCalledWith("/api/shares/create/other/nested/file.txt", {
      body: {},
      method: "POST",
    });
  });

  it("does not mark the node as shared when the request fails", async () => {
    vi.spyOn(m, "request").mockRejectedValue(new Error("network error"));
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "file.txt" });

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
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "report.txt", share });

    await service.revokeShare(fsNode);

    expect(request).toHaveBeenCalledWith(`/api/shares/${share.id}/revoke`, {
      method: "POST",
    });
    expect(fsNode.share).toBeNull();
    expect(fsNode.is_shared).toBe(false);
  });

  it("does nothing when the node has no active share", async () => {
    const request = vi.spyOn(m, "request");
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "file.txt" });

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
    const service = createService("/docs");
    const fsNode = new DashboardFsNode({ name: "file.txt", share });

    await expect(service.revokeShare(fsNode)).rejects.toThrow("network error");
    expect(fsNode.share).toEqual(share);
    expect(fsNode.is_shared).toBe(true);
  });
});
