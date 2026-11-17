import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../bootstrap/modal", () => ({
  Modal: { modalHeader: {} },
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));
vi.mock("@polyfile/core/ui-kit/button", () => ({
  default: {
    view(vnode) {
      return vnode.children;
    },
  },
}));

import { closeModal } from "../../bootstrap/modal";
import { RestoreMonitorModal } from "../restore_monitor_modal";

const ENTRY_A = { id: "11111111-1111-1111-1111-111111111111", name: "a.txt", type: "file" };
const ENTRY_B = { id: "22222222-2222-2222-2222-222222222222", name: "b.txt", type: "file" };

const createService = () => ({
  restore: vi.fn(),
});

const createVnode = (service, entries = [ENTRY_A]) => ({
  attrs: { modalId: ["modal"], service, entries },
  state: {},
});

const init = (vnode) => {
  RestoreMonitorModal.oninit(vnode);
  return vnode;
};

const statusOf = (vnode, index) => vnode.state.jobs[index].status;

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(closeModal).mockClear();
});

describe("RestoreMonitorModal.run()", () => {
  it("restores every entry and reports completion", async () => {
    const service = createService();
    service.restore.mockResolvedValue({ notices: [], restored_entries: [] });
    const vnode = init(createVnode(service, [ENTRY_A, ENTRY_B]));

    await RestoreMonitorModal.run(vnode);

    expect(service.restore).toHaveBeenCalledTimes(2);
    expect(statusOf(vnode, 0)).toBe("done");
    expect(statusOf(vnode, 1)).toBe("done");
    expect(RestoreMonitorModal.isFinished(vnode)).toBe(true);
  });

  it("stops at a name conflict and waits for the user", async () => {
    const service = createService();
    const conflict = new Error("exists");
    conflict.response = { error_id: "FsNodeExistsError" };
    service.restore.mockRejectedValueOnce(conflict).mockResolvedValueOnce({});
    const vnode = init(createVnode(service, [ENTRY_A, ENTRY_B]));

    await RestoreMonitorModal.run(vnode);

    expect(statusOf(vnode, 0)).toBe("conflict");
    expect(statusOf(vnode, 1)).toBe("pending");
    expect(RestoreMonitorModal.isFinished(vnode)).toBe(false);
  });

  it("marks non-conflict failures as errors and continues", async () => {
    const service = createService();
    service.restore.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce({});
    const vnode = init(createVnode(service, [ENTRY_A, ENTRY_B]));

    await RestoreMonitorModal.run(vnode);

    expect(statusOf(vnode, 0)).toBe("error");
    expect(statusOf(vnode, 1)).toBe("done");
  });

  it("collects implicit restores and notices", async () => {
    const service = createService();
    service.restore.mockResolvedValue({
      notices: [{ type: "merged", name: "docs" }],
      restored_entries: [{ id: "parent", name: "docs" }],
    });
    const vnode = init(createVnode(service));

    await RestoreMonitorModal.run(vnode);

    expect(vnode.state.notices).toEqual([{ type: "merged", name: "docs" }]);
    expect(vnode.state.implicit).toEqual([{ id: "parent", name: "docs" }]);
  });
});

describe("RestoreMonitorModal conflict resolution", () => {
  it("retries with rename when 'Keep both' is chosen", async () => {
    const service = createService();
    const conflict = new Error("exists");
    conflict.response = { error_id: "FsNodeExistsError" };
    service.restore.mockRejectedValueOnce(conflict).mockResolvedValueOnce({});
    const vnode = init(createVnode(service));

    await RestoreMonitorModal.run(vnode);
    await RestoreMonitorModal.resolveConflict(vnode, "rename");

    expect(service.restore).toHaveBeenLastCalledWith(ENTRY_A.id, "rename");
    expect(statusOf(vnode, 0)).toBe("done");
  });

  it("marks the entry skipped when the user skips it", async () => {
    const service = createService();
    const conflict = new Error("exists");
    conflict.response = { error_id: "FsNodeExistsError" };
    service.restore.mockRejectedValueOnce(conflict).mockResolvedValueOnce({});
    const vnode = init(createVnode(service));

    await RestoreMonitorModal.run(vnode);
    await RestoreMonitorModal.resolveConflict(vnode, "skip");

    expect(statusOf(vnode, 0)).toBe("skipped");
    expect(RestoreMonitorModal.isFinished(vnode)).toBe(true);
  });
});

describe("RestoreMonitorModal.stop()", () => {
  it("prevents further processing", async () => {
    const service = createService();
    const vnode = init(createVnode(service, [ENTRY_A]));
    RestoreMonitorModal.stop(vnode);

    await RestoreMonitorModal.run(vnode);

    expect(service.restore).not.toHaveBeenCalled();
  });
});
