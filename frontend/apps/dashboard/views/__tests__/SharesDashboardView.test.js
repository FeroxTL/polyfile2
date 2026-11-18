import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../components/DashboardShell", () => ({ DashboardShell: {} }));
vi.mock("../../modals/PermanentDeleteShareModal", () => ({
  showPermanentDeleteShareModal: vi.fn(),
}));
vi.mock("../../bootstrap/modal", () => ({
  showModal: vi.fn(),
  closeModal: vi.fn(),
}));

import m from "mithril";
import { showPermanentDeleteShareModal } from "../../modals/PermanentDeleteShareModal";
import { showModal } from "../../bootstrap/modal";
import { ShareList } from "../../services/ShareList";
import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import { FILES_DASHBOARD_URL } from "../../constants/endpoints";
import { ShareDirectoryModal } from "../../modals/ShareDirectoryModal";
import { SharesDashboardView } from "../SharesDashboardView";

const createService = () => ({
  items: [],
  status: "active",
  page: 2,
  pageSize: 25,
  isLoading: false,
  error: null,
  load: vi.fn().mockResolvedValue({}),
  revoke: vi.fn().mockResolvedValue(),
  deletePermanent: vi.fn().mockResolvedValue(),
});

const createVnode = (service = createService()) => ({
  state: { service },
});

beforeEach(() => {
  DashboardFsNodeList.current = null;
  DashboardFsNodeList.ancestors = [];
  DashboardFsNodeList.elements = [];
  DashboardFsNodeList.error = null;
  DashboardFsNodeList.xhr = null;
  DashboardFsNodeList.pendingPath = null;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(showPermanentDeleteShareModal).mockClear();
  vi.mocked(showModal).mockClear();
});

describe("SharesDashboardView filters", () => {
  it("loads the default filter on init", () => {
    const load = vi.spyOn(ShareList, "load").mockResolvedValue({});
    const vnode = { state: {} };

    SharesDashboardView.oninit(vnode);

    expect(vnode.state.service).toBe(ShareList);
    expect(load).toHaveBeenCalledWith({ status: "all", page: 1, pageSize: 25 });
  });

  it("reloads the first page when the status filter changes", () => {
    const service = createService();
    const vnode = createVnode(service);

    SharesDashboardView.setStatus(vnode, "revoked");

    expect(service.load).toHaveBeenCalledWith({
      status: "revoked",
      page: 1,
      pageSize: 25,
    });
  });
});

describe("SharesDashboardView actions", () => {
  it("revokes a share and reloads the current filtered page", async () => {
    const service = createService();
    const vnode = createVnode(service);
    const share = { id: "token" };

    SharesDashboardView.revokeShare(vnode, share);

    await vi.waitFor(() => {
      expect(service.load).toHaveBeenCalledWith({
        status: "active",
        page: 2,
        pageSize: 25,
      });
    });
    expect(service.revoke).toHaveBeenCalledWith(share);
  });

  it("resolves the path lazily and navigates to a shared directory", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      current: {
        id: "33333333-3333-3333-3333-333333333333",
        parent_id: "22222222-2222-2222-2222-222222222222",
        name: "nested",
        type: "directory",
      },
      ancestors: [{ id: "11111111-1111-1111-1111-111111111111", name: "root_dir" }],
      children: [],
    });
    const set = vi.spyOn(m.route, "set").mockReturnValue();
    const share = {
      id: "token",
      status: "active",
      root_fs_node: { id: "33333333-3333-3333-3333-333333333333", type: "directory" },
    };

    await SharesDashboardView.navigateToNode(share);

    expect(request).toHaveBeenCalledTimes(1);
    expect(request.mock.calls[0][0]).toBe(
      "/api/v1/fs-node/33333333-3333-3333-3333-333333333333/",
    );
    expect(set).toHaveBeenCalledWith(FILES_DASHBOARD_URL, {
      path: "/root_dir/nested",
    });
    // The route match reuses the loaded directory instead of fetching it by path.
    expect(DashboardFsNodeList.consumePendingPath("/root_dir/nested")).toBe(true);
  });

  it("navigates to the parent directory for a shared file", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      current: {
        id: "44444444-4444-4444-4444-444444444444",
        parent_id: "33333333-3333-3333-3333-333333333333",
        name: "file.txt",
        type: "file",
      },
      ancestors: [
        { id: "11111111-1111-1111-1111-111111111111", name: "root_dir" },
        { id: "33333333-3333-3333-3333-333333333333", name: "nested" },
      ],
      children: [],
    });
    const set = vi.spyOn(m.route, "set").mockReturnValue();
    const share = {
      id: "token",
      status: "active",
      root_fs_node: { id: "44444444-4444-4444-4444-444444444444", type: "file" },
    };

    await SharesDashboardView.navigateToNode(share);

    expect(request).toHaveBeenCalledTimes(1);
    expect(set).toHaveBeenCalledWith(FILES_DASHBOARD_URL, {
      path: "/root_dir/nested",
    });
    // A file is not the directory it navigates to, so nothing is preloaded.
    expect(DashboardFsNodeList.pendingPath).toBeNull();
  });

  it("does not navigate when the shared node can not be resolved", async () => {
    vi.spyOn(m, "request").mockRejectedValue(new Error("404"));
    const set = vi.spyOn(m.route, "set").mockReturnValue();
    const share = {
      id: "token",
      status: "active",
      root_fs_node: { id: "33333333-3333-3333-3333-333333333333", type: "directory" },
    };

    await SharesDashboardView.navigateToNode(share);

    expect(set).not.toHaveBeenCalled();
  });

  it("does not navigate when the share has no node id", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({});
    const set = vi.spyOn(m.route, "set").mockReturnValue();

    await SharesDashboardView.navigateToNode({ id: "token", root_fs_node: {} });

    expect(request).not.toHaveBeenCalled();
    expect(set).not.toHaveBeenCalled();
  });

  it("opens the share modal with share data and callbacks", () => {
    const share = {
      id: "token",
      status: "active",
      url: "https://example.com/s/token/",
      root_fs_node: {
        id: "11111111-1111-1111-1111-111111111111",
        name: "file.txt",
        type: "file",
      },
    };

    SharesDashboardView.openShareModal(createVnode(), share);

    expect(showModal).toHaveBeenCalledTimes(1);
    const [[ModalComponent, attrs]] = showModal.mock.calls;
    expect(ModalComponent).toBe(ShareDirectoryModal);
    expect(attrs.share).toBe(share);
    expect(attrs.nodeId).toBe("11111111-1111-1111-1111-111111111111");
    expect(attrs.type).toBe("file");
    expect(typeof attrs.onUpdate).toBe("function");
  });

  it("keeps the share row in sync after the modal updates it", () => {
    const share = {
      id: "old-token",
      status: "expired",
      url: null,
      expires_at: "2020-01-01T00:00:00.000Z",
      revoked_at: null,
      root_fs_node: {
        id: "11111111-1111-1111-1111-111111111111",
        name: "file.txt",
        type: "file",
      },
    };

    SharesDashboardView.openShareModal(createVnode(), share);

    const [[, attrs]] = showModal.mock.calls;

    attrs.onUpdate({
      id: "new-token",
      url: "https://example.com/s/new-token/",
      status: "active",
      expires_at: "2030-01-01T00:00:00.000Z",
      revoked_at: null,
    });

    expect(share).toMatchObject({
      id: "new-token",
      status: "active",
      url: "https://example.com/s/new-token/",
      expires_at: "2030-01-01T00:00:00.000Z",
      revoked_at: null,
    });

    attrs.onUpdate(null);

    expect(share.status).toBe("revoked");
    expect(share.url).toBeNull();
  });

  it("renders share actions for shares", () => {
    const share = {
      id: "token",
      status: "active",
      url: "https://example.com/s/token/",
      root_fs_node: { name: "file.txt", type: "file" },
    };

    const item = SharesDashboardView.renderItem(createVnode(), share);
    const buttons = JSON.stringify(item);

    expect(buttons).toContain("fa-trash");
  });

  it("asks for confirmation before deleting a share permanently", async () => {
    const service = createService();
    const vnode = createVnode(service);
    const share = { id: "token" };

    SharesDashboardView.deleteShare(vnode, share);

    expect(showPermanentDeleteShareModal).toHaveBeenCalledTimes(1);
    const [[attrs]] = showPermanentDeleteShareModal.mock.calls;

    await attrs.onConfirm();

    expect(service.deletePermanent).toHaveBeenCalledWith(share);
    expect(service.load).toHaveBeenCalledWith({
      status: "active",
      page: 2,
      pageSize: 25,
    });
  });
});
