import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ShareService } from "../ShareService";

describe("ShareService.create()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a share for the given node id", async () => {
    const share = { id: "token", url: "https://example.com/s/token/" };
    const request = vi.spyOn(m, "request").mockResolvedValue(share);

    const data = await ShareService.create("11111111-1111-1111-1111-111111111111");

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      body: { node_id: "11111111-1111-1111-1111-111111111111" },
      method: "POST",
    });
    expect(data.id).toBe("token");
  });

  it("sends expiration when provided", async () => {
    const expiresAt = "2030-01-02T03:04:00.000Z";
    const request = vi.spyOn(m, "request").mockResolvedValue({});

    await ShareService.create("11111111-1111-1111-1111-111111111111", expiresAt);

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      method: "POST",
      body: { node_id: "11111111-1111-1111-1111-111111111111", expires_at: expiresAt },
    });
  });

  it("sends null to clear an existing expiration", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});

    await ShareService.create("11111111-1111-1111-1111-111111111111", null);

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      method: "POST",
      body: { node_id: "11111111-1111-1111-1111-111111111111", expires_at: null },
    });
  });
});

describe("ShareService.revoke()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("deletes the share by token", async () => {
    const share = { id: "token", url: "https://example.com/s/token/" };
    const request = vi.spyOn(m, "request").mockResolvedValue();

    await ShareService.revoke(share);

    expect(request).toHaveBeenCalledWith("/api/shares/token/revoke", {
      method: "POST",
    });
  });

  it("does nothing when share has no id", async () => {
    const request = vi.spyOn(m, "request");

    await ShareService.revoke(null);
    await ShareService.revoke({});

    expect(request).not.toHaveBeenCalled();
  });
});
