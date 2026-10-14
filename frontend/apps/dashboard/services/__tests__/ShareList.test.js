import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ShareListService } from "../ShareList";

const createService = () => new ShareListService();

describe("ShareListService.load()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads shares with the requested filters and stores the response", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      items: [{ id: "token" }],
      total: 1,
      page: 2,
      page_size: 10,
    });
    const service = createService();

    const data = await service.load({ status: "expired", page: 2, pageSize: 10 });

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      method: "GET",
      params: {
        status: "expired",
        page: 2,
        page_size: 10,
      },
    });
    expect(data.items).toEqual([{ id: "token" }]);
    expect(service.items).toEqual([{ id: "token" }]);
    expect(service.total).toBe(1);
    expect(service.page).toBe(2);
    expect(service.pageSize).toBe(10);
    expect(service.status).toBe("expired");
    expect(service.isLoading).toBe(false);
  });

  it("uses the current filters and page size when options are omitted", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      items: [],
      total: 0,
      page: 3,
      page_size: 25,
    });
    const service = createService();
    service.status = "revoked";
    service.page = 3;

    await service.load();

    expect(request).toHaveBeenCalledWith("/api/shares/", {
      method: "GET",
      params: {
        status: "revoked",
        page: 3,
        page_size: 25,
      },
    });
  });

  it("records load errors and rethrows them", async () => {
    const error = new Error("network error");
    vi.spyOn(m, "request").mockRejectedValue(error);
    const service = createService();

    await expect(service.load()).rejects.toThrow("network error");

    expect(service.error).toBe(error);
    expect(service.isLoading).toBe(false);
  });
});

describe("ShareListService actions", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("revokes a share by token", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue();
    const service = createService();

    await service.revoke({ id: "token" });

    expect(request).toHaveBeenCalledWith("/api/shares/token/revoke", {
      method: "POST",
    });
  });

  it("permanently deletes a share by token", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue();
    const service = createService();

    await service.deletePermanent({ id: "token" });

    expect(request).toHaveBeenCalledWith("/api/shares/token/delete", {
      method: "DELETE",
    });
  });

  it("does not send requests without a share token", async () => {
    const request = vi.spyOn(m, "request");
    const service = createService();

    await service.revoke({});
    await service.deletePermanent(null);

    expect(request).not.toHaveBeenCalled();
  });
});
