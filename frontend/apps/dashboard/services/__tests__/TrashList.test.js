import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { TrashListService } from "../TrashList";

const ENTRY_A = "11111111-1111-1111-1111-111111111111";
const ENTRY_B = "22222222-2222-2222-2222-222222222222";

const createService = () => new TrashListService();

describe("TrashListService.load()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads entries and resets the selection", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      entries: [{ id: ENTRY_A, name: "a.txt", type: "file" }],
    });
    const service = createService();
    service.selected.add(ENTRY_B);

    await service.load();

    expect(request).toHaveBeenCalledWith("/api/v1/trash/", { method: "GET" });
    expect(service.entries).toEqual([{ id: ENTRY_A, name: "a.txt", type: "file" }]);
    expect(service.selected.size).toBe(0);
    expect(service.isLoading).toBe(false);
  });

  it("stores the error and rethrows on failure", async () => {
    const error = new Error("boom");
    vi.spyOn(m, "request").mockRejectedValue(error);
    const service = createService();

    await expect(service.load()).rejects.toThrow("boom");

    expect(service.error).toBe(error);
    expect(service.isLoading).toBe(false);
  });
});

describe("TrashListService selection", () => {
  it("toggles and clears the selection", () => {
    const service = createService();
    service.entries = [
      { id: ENTRY_A, name: "a.txt", type: "file" },
      { id: ENTRY_B, name: "b", type: "directory" },
    ];

    service.toggleSelected(ENTRY_A);
    service.toggleSelected(ENTRY_B);
    expect(service.getSelectedEntries()).toEqual(service.entries);

    service.toggleSelected(ENTRY_A);
    expect(service.getSelectedEntries()).toEqual([service.entries[1]]);

    service.clearSelected();
    expect(service.selected.size).toBe(0);
  });
});

describe("TrashListService.restore()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts on_conflict and drops the entry on success", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      node: { id: ENTRY_A },
      restored_entries: [],
      notices: [],
    });
    const service = createService();
    service.entries = [{ id: ENTRY_A, name: "a.txt", type: "file" }];
    service.selected.add(ENTRY_A);

    const data = await service.restore(ENTRY_A, "rename");

    expect(request).toHaveBeenCalledWith(`/api/v1/trash/${ENTRY_A}/restore`, {
      method: "POST",
      body: { on_conflict: "rename" },
    });
    expect(data.notices).toEqual([]);
    expect(service.entries).toEqual([]);
    expect(service.selected.size).toBe(0);
  });

  it("keeps the entry when restore conflicts", async () => {
    const error = new Error("conflict");
    error.response = { error_id: "FsNodeExistsError" };
    vi.spyOn(m, "request").mockRejectedValue(error);
    const service = createService();
    service.entries = [{ id: ENTRY_A, name: "a.txt", type: "file" }];

    await expect(service.restore(ENTRY_A)).rejects.toThrow("conflict");

    expect(service.entries).toHaveLength(1);
  });
});

describe("TrashListService.deletePermanent() and empty()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("deletes one entry and drops it from the list", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({ job_id: "job" });
    const service = createService();
    service.entries = [
      { id: ENTRY_A, name: "a.txt", type: "file" },
      { id: ENTRY_B, name: "b", type: "directory" },
    ];

    await service.deletePermanent(ENTRY_A);

    expect(request).toHaveBeenCalledWith(`/api/v1/trash/${ENTRY_A}/`, { method: "DELETE" });
    expect(service.entries).toEqual([{ id: ENTRY_B, name: "b", type: "directory" }]);
  });

  it("empties the whole trash", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({ job_ids: ["job"] });
    const service = createService();
    service.entries = [{ id: ENTRY_A, name: "a.txt", type: "file" }];
    service.selected.add(ENTRY_A);

    await service.empty();

    expect(request).toHaveBeenCalledWith("/api/v1/trash/empty", { method: "POST" });
    expect(service.entries).toEqual([]);
    expect(service.selected.size).toBe(0);
  });
});
