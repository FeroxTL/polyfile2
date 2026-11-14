import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";
import stream from "mithril/stream";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { closeModal } from "../../bootstrap/modal";
import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import { sendCreateDirectoryRequest } from "../create_directory_modal";

const PARENT_ID = "11111111-1111-1111-1111-111111111111";

const createVnode = (name = "New directory") => ({
  attrs: { modalId: ["modal"] },
  state: { error: null, valueStream: stream(name), fieldErrors: [] },
});

describe("sendCreateDirectoryRequest()", () => {
  beforeEach(() => {
    DashboardFsNodeList.current = null;
    DashboardFsNodeList.elements = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
  });

  it("creates a directory by parent id and name", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: "22222222-2222-2222-2222-222222222222",
      parent_id: PARENT_ID,
      name: "New directory",
      type: "directory",
    });
    DashboardFsNodeList.current = { id: PARENT_ID };

    await sendCreateDirectoryRequest(createVnode());

    expect(request).toHaveBeenCalledWith({
      method: "POST",
      url: "/api/v1/fs-node/mkdir",
      body: { parent_id: PARENT_ID, name: "New directory" },
    });
    expect(closeModal).toHaveBeenCalled();
    expect(DashboardFsNodeList.elements).toHaveLength(1);
    expect(DashboardFsNodeList.elements[0].id).toBe("22222222-2222-2222-2222-222222222222");
  });

  it("creates a directory in the virtual root when there is no current id", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      id: "22222222-2222-2222-2222-222222222222",
      parent_id: null,
      name: "New directory",
      type: "directory",
    });
    DashboardFsNodeList.current = { id: null };

    await sendCreateDirectoryRequest(createVnode());

    expect(request).toHaveBeenCalledWith({
      method: "POST",
      url: "/api/v1/fs-node/mkdir",
      body: { parent_id: null, name: "New directory" },
    });
  });

  it("keeps the modal open and shows the error on failure", async () => {
    vi.spyOn(m, "request").mockRejectedValue({
      code: 400,
      response: { detail: { name: ["Name contains reserved characters"] } },
    });

    const vnode = createVnode();
    await sendCreateDirectoryRequest(vnode);

    expect(closeModal).not.toHaveBeenCalled();
    expect(vnode.state.fieldErrors.length).toBeGreaterThan(0);
  });
});
