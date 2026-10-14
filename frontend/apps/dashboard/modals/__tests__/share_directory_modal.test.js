import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { closeModal } from "../../bootstrap/modal";
import { ShareDirectoryModal } from "../share_directory_modal";

// Mock ShareService
const { mockCreate, mockRevoke } = vi.hoisted(() => ({
  mockCreate: vi.fn(),
  mockRevoke: vi.fn(),
}));

vi.mock("../../services/ShareService", () => ({
  ShareService: {
    create: mockCreate,
    revoke: mockRevoke,
  },
}));

const activeShare = {
  id: "4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10",
  url: "https://example.com/s/4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10/",
  expires_at: "2030-01-01T00:00:00.000Z",
};

const createVnode = (attrs = {}) => {
  const shareData = attrs.share === null ? null : (attrs.share || activeShare);

  return {
    attrs: {
      share: shareData,
      path: attrs.path || "/docs/file.txt",
      type: attrs.type || "file",
      onCreate: attrs.onCreate || vi.fn(),
      onUpdate: attrs.onUpdate || vi.fn(),
      onRevoke: attrs.onRevoke || vi.fn(),
      modalId: ["modal"],
    },
    state: {
      shareLink: shareData?.url || "",
      formExpiresAt: attrs.formExpiresAt || "",
      expiresAt: "",
      loading: false,
      error: null,
      copied: false,
      copyError: null,
      revoked: false,
      share: shareData,
    },
  };
};

describe("ShareDirectoryModal.submit()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
    mockCreate.mockClear();
    mockRevoke.mockClear();
  });

  it("creates a share with the selected expiration", async () => {
    const mockData = {
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: "2030-01-02T03:04:00.000Z",
    };
    mockCreate.mockResolvedValue(mockData);

    const onUpdate = vi.fn();
    const vnode = createVnode({ share: null, onUpdate });
    vnode.state.formExpiresAt = "2030-01-02T03:04";
    const expiresAt = new Date(vnode.state.formExpiresAt).toISOString();

    ShareDirectoryModal.submit(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.loading).toBe(false);
    });
    expect(onUpdate).toHaveBeenCalledWith(mockData);
    expect(vnode.state.shareLink).toBe(mockData.url);
    expect(vnode.state.error).toBeNull();
  });

  it("updates an active share expiration without rotating its link", async () => {
    const mockData = {
      id: activeShare.id,
      url: activeShare.url,
      expires_at: "2030-05-06T07:08:00.000Z",
    };
    mockCreate.mockResolvedValue(mockData);

    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });
    vnode.state.formExpiresAt = "2030-05-06T07:08";
    const expiresAt = new Date(vnode.state.formExpiresAt).toISOString();

    ShareDirectoryModal.submit(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.loading).toBe(false);
    });
    expect(onUpdate).toHaveBeenCalledWith(mockData);
    expect(vnode.state.shareLink).toBe(activeShare.url);
  });

  it("sends null when the expiration is cleared", async () => {
    const mockData = {
      id: activeShare.id,
      url: activeShare.url,
      expires_at: null,
    };
    mockCreate.mockResolvedValue(mockData);

    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });
    vnode.state.formExpiresAt = "";

    ShareDirectoryModal.submit(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.loading).toBe(false);
    });
    expect(onUpdate).toHaveBeenCalledWith(mockData);
    expect(vnode.state.formExpiresAt).toBe("");
  });
});

describe("ShareDirectoryModal.revoke()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
    mockCreate.mockClear();
    mockRevoke.mockClear();
  });

  it("revokes the share, clears the link and shows the revoked state", async () => {
    mockRevoke.mockResolvedValue();

    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });

    ShareDirectoryModal.revoke(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.revoked).toBe(true);
    });
    expect(onUpdate).toHaveBeenCalledWith(null);
    expect(vnode.state.shareLink).toBe("");
    expect(vnode.state.loading).toBe(false);
    expect(vnode.state.error).toBeNull();
    expect(closeModal).not.toHaveBeenCalled();
  });

  it("shows an error and keeps the modal open when revocation fails", async () => {
    mockRevoke.mockRejectedValue({
      response: { detail: "Share does not exist." },
    });

    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });
    vnode.state.share = activeShare;

    ShareDirectoryModal.revoke(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.error).toBe("Share does not exist.");
    });
    expect(closeModal).not.toHaveBeenCalled();
    expect(vnode.state.shareLink).toBe(activeShare.url);
    expect(vnode.state.loading).toBe(false);
    expect(vnode.state.revoked).toBe(false);
  });

  it("ignores clicks while another share request is running", () => {
    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });
    vnode.state.loading = true;

    ShareDirectoryModal.revoke(vnode);

    expect(onUpdate).not.toHaveBeenCalled();
  });
});
