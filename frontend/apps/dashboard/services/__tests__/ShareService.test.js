import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ShareService } from "../ShareService";

describe("ShareService.create()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates a share for the given path", async () => {
    const share = { id: "token", url: "https://example.com/s/token/" };
    const request = vi.spyOn(m, "request").mockResolvedValue({ share });

    const data = await ShareService.create("/docs/file.txt");

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/file.txt", {
      body: {},
      method: "POST",
    });
    expect(data.share).toEqual(share);
  });

  it("sends expiration when provided", async () => {
    const expiresAt = "2030-01-02T03:04:00.000Z";
    const request = vi.spyOn(m, "request").mockResolvedValue({});

    await ShareService.create("/docs/file.txt", expiresAt);

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/file.txt", {
      method: "POST",
      body: { expires_at: expiresAt },
    });
  });

  it("sends null to clear an existing expiration", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});

    await ShareService.create("/docs/file.txt", null);

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/file.txt", {
      method: "POST",
      body: { expires_at: null },
    });
  });

  it("encodes special characters in the path", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});

    await ShareService.create("/docs/report #1.txt");

    expect(request).toHaveBeenCalledWith("/api/shares/create/docs/report%20%231.txt", {
      "body": {},
      method: "POST",
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
