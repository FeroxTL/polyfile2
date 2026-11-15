import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { closeModal } from "../../bootstrap/modal";
import {
  PRESET_CUSTOM,
  PRESET_NEVER,
  toDateTimeLocalValue,
} from "../share_expiration";
import { ShareDirectoryModal, isShareActive, resolveShareStatus } from "../share_directory_modal";

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
  status: "active",
  expires_at: "2030-01-01T00:00:00.000Z",
  revoked_at: null,
};

const savedShare = {
  ...activeShare,
  expires_at: "2030-01-08T00:00:00.000Z",
};

const AUTO_SAVE_DEBOUNCE_MS = 500;

const createVnode = (attrs = {}) => {
  const shareData = attrs.share === null ? null : (attrs.share || activeShare);
  const vnode = {
    attrs: {
      share: shareData,
      nodeId: attrs.nodeId || "11111111-1111-1111-1111-111111111111",
      type: attrs.type || "file",
      onUpdate: attrs.onUpdate || vi.fn(),
      modalId: ["modal"],
    },
    state: {},
  };

  ShareDirectoryModal.oninit(vnode);

  if (typeof attrs.formExpiresAt === "string") {
    vnode.state.formExpiresAt = attrs.formExpiresAt;
  }

  return vnode;
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.mocked(closeModal).mockClear();
  mockCreate.mockClear();
  mockRevoke.mockClear();
});

describe("ShareDirectoryModal.submit()", () => {
  it("creates a share with the selected expiration", async () => {
    const mockData = {
      id: "token",
      url: "https://example.com/s/token/",
      status: "active",
      expires_at: "2030-01-02T03:04:00.000Z",
      revoked_at: null,
    };
    mockCreate.mockResolvedValue(mockData);

    const onUpdate = vi.fn();
    const vnode = createVnode({ share: null, onUpdate });
    vnode.state.preset = PRESET_CUSTOM;
    vnode.state.formExpiresAt = "2030-01-02T03:04";
    const expiresAt = new Date(vnode.state.formExpiresAt).toISOString();

    ShareDirectoryModal.submit(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.loading).toBe(false);
    });
    expect(mockCreate).toHaveBeenCalledWith(vnode.attrs.nodeId, expiresAt);
    expect(onUpdate).toHaveBeenCalledWith(mockData);
    expect(vnode.state.shareLink).toBe(mockData.url);
    expect(vnode.state.error).toBeNull();
  });

  it("rejects a custom expiration in the past", () => {
    const vnode = createVnode({ share: null });
    vnode.state.preset = PRESET_CUSTOM;
    vnode.state.formExpiresAt = "2020-01-02T03:04";

    ShareDirectoryModal.submit(vnode);

    expect(mockCreate).not.toHaveBeenCalled();
    expect(vnode.state.expirationError).toBe("Expiration must be in the future.");
  });

  it("sends null when the expiration is set to never", async () => {
    const mockData = {
      id: activeShare.id,
      url: activeShare.url,
      status: "active",
      expires_at: null,
      revoked_at: null,
    };
    mockCreate.mockResolvedValue(mockData);

    const vnode = createVnode({ share: null });
    vnode.state.preset = PRESET_NEVER;
    vnode.state.formExpiresAt = "";

    ShareDirectoryModal.submit(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.loading).toBe(false);
    });
    expect(mockCreate).toHaveBeenCalledWith(vnode.attrs.nodeId, null);
  });
});

describe("ShareDirectoryModal expiration presets", () => {
  it("saves a selected preset immediately", async () => {
    mockCreate.mockResolvedValue(savedShare);

    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });
    const originalForm = vnode.state.formExpiresAt;

    ShareDirectoryModal.setPreset(vnode, "7d");

    await vi.waitFor(() => {
      expect(vnode.state.saveStatus).toBe("saved");
    });
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate).toHaveBeenCalledWith(vnode.attrs.nodeId, expect.any(String));
    expect(vnode.state.formExpiresAt).not.toBe(originalForm);
    expect(vnode.state.savedFormExpiresAt).toBe(vnode.state.formExpiresAt);
    expect(onUpdate).toHaveBeenCalledWith(savedShare);
  });

  it("saves 'never expires' as null", async () => {
    mockCreate.mockResolvedValue({ ...activeShare, expires_at: null });

    const vnode = createVnode();

    ShareDirectoryModal.setPreset(vnode, PRESET_NEVER);

    await vi.waitFor(() => {
      expect(vnode.state.saveStatus).toBe("saved");
    });
    expect(mockCreate).toHaveBeenCalledWith(vnode.attrs.nodeId, null);
    expect(vnode.state.formExpiresAt).toBe("");
  });

  it("does not save when the value did not change", () => {
    const vnode = createVnode();

    ShareDirectoryModal.setPreset(vnode, PRESET_CUSTOM);

    expect(mockCreate).not.toHaveBeenCalled();
  });

  it("debounces custom expiration saves", async () => {
    vi.useFakeTimers();
    mockCreate.mockResolvedValue(savedShare);

    const vnode = createVnode();
    ShareDirectoryModal.setPreset(vnode, PRESET_CUSTOM);
    ShareDirectoryModal.setCustomExpiration(vnode, "2030-02-03T04:05");
    ShareDirectoryModal.setCustomExpiration(vnode, "2030-02-03T04:06");

    expect(mockCreate).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(AUTO_SAVE_DEBOUNCE_MS);

    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate.mock.calls[0][1]).toBe(new Date("2030-02-03T04:06").toISOString());
  });

  it("rejects a custom date in the past without saving", async () => {
    vi.useFakeTimers();

    const vnode = createVnode();
    ShareDirectoryModal.setPreset(vnode, PRESET_CUSTOM);
    ShareDirectoryModal.setCustomExpiration(vnode, "2020-01-01T00:00");

    await vi.advanceTimersByTimeAsync(AUTO_SAVE_DEBOUNCE_MS);

    expect(mockCreate).not.toHaveBeenCalled();
    expect(vnode.state.expirationError).toBe("Expiration must be in the future.");
  });

  it("reactivates a revoked share that had no expiration when 'never' is chosen", async () => {
    const revokedShare = {
      id: "token",
      url: null,
      status: "revoked",
      expires_at: null,
      revoked_at: "2021-01-01T00:00:00.000Z",
    };
    mockCreate.mockResolvedValue({ ...activeShare, expires_at: null });

    const vnode = createVnode({ share: revokedShare });
    expect(vnode.state.preset).toBe("");

    const body = JSON.stringify(ShareDirectoryModal.renderBody(vnode));
    expect(body).toContain("Choose expiration…");

    ShareDirectoryModal.setPreset(vnode, PRESET_NEVER);

    await vi.waitFor(() => {
      expect(vnode.state.saveStatus).toBe("saved");
    });
    expect(mockCreate).toHaveBeenCalledWith(vnode.attrs.nodeId, null);
  });

  it("flushes a pending custom edit when the modal is removed", () => {
    vi.useFakeTimers();
    mockCreate.mockResolvedValue(savedShare);

    const vnode = createVnode();
    ShareDirectoryModal.setPreset(vnode, PRESET_CUSTOM);
    ShareDirectoryModal.setCustomExpiration(vnode, "2030-02-03T04:06");

    ShareDirectoryModal.onremove(vnode);

    expect(mockCreate).toHaveBeenCalledWith(
      vnode.attrs.nodeId,
      new Date("2030-02-03T04:06").toISOString()
    );
  });

  it("rolls back to the saved value when auto-save fails", async () => {
    mockCreate.mockRejectedValue({ response: { detail: "Share is locked." } });

    const vnode = createVnode();
    const originalForm = vnode.state.formExpiresAt;

    ShareDirectoryModal.setPreset(vnode, "7d");

    await vi.waitFor(() => {
      expect(vnode.state.error).toBe("Share is locked.");
    });
    expect(vnode.state.preset).toBe(PRESET_CUSTOM);
    expect(vnode.state.formExpiresAt).toBe(originalForm);
    expect(vnode.state.saveStatus).toBeNull();
  });

  it("renders presets, the saved date and the save indicator", () => {
    const vnode = createVnode();
    vnode.state.saveStatus = "saving";

    const body = JSON.stringify(ShareDirectoryModal.renderBody(vnode));

    expect(body).toContain("Never expires");
    expect(body).toContain("7 days");
    expect(body).toContain("Custom…");
    expect(body).toContain("Expires on");
    expect(body).toContain("Saving…");
  });
});

describe("ShareDirectoryModal status", () => {
  const expiredShare = {
    id: "token",
    url: null,
    status: "expired",
    expires_at: "2020-01-01T00:00:00.000Z",
    revoked_at: null,
  };

  it("shows an expired notice and badge for an expired share", () => {
    const vnode = createVnode({ share: expiredShare });

    const body = JSON.stringify(ShareDirectoryModal.renderBody(vnode));

    expect(body).toContain("has expired");
    expect(body).toContain("Expired");
    expect(body).toContain("Expired on");
  });

  it("derives the expired status from expires_at when the API omits status", () => {
    const share = {
      id: "token",
      url: "https://example.com/s/token/",
      expires_at: "2020-01-01T00:00:00.000Z",
    };

    expect(resolveShareStatus(share)).toBe("expired");
    expect(isShareActive(share)).toBe(false);

    const vnode = createVnode({ share });
    const body = JSON.stringify(ShareDirectoryModal.renderBody(vnode));

    expect(body).toContain("has expired");
    expect(body).toContain("\"disabled\":true");
  });

  it("prioritizes revocation over expiration", () => {
    const share = {
      id: "token",
      url: null,
      status: "revoked",
      expires_at: "2020-01-01T00:00:00.000Z",
      revoked_at: "2021-01-01T00:00:00.000Z",
    };

    expect(resolveShareStatus(share)).toBe("revoked");

    const body = JSON.stringify(ShareDirectoryModal.renderBody(createVnode({ share })));

    expect(body).toContain("has been revoked");
  });

  it("does not show a lifecycle notice for an active share", () => {
    const body = JSON.stringify(ShareDirectoryModal.renderBody(createVnode()));

    expect(body).toContain("Active");
    expect(body).not.toContain("has expired");
    expect(body).not.toContain("has been revoked");
  });
});

describe("ShareDirectoryModal.revoke()", () => {
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
    expect(vnode.state.formExpiresAt).toBe("");
    expect(vnode.state.preset).toBe(PRESET_NEVER);
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

  it("ignores clicks while an expiration is being saved", () => {
    const onUpdate = vi.fn();
    const vnode = createVnode({ onUpdate });
    vnode.state.saving = true;

    ShareDirectoryModal.revoke(vnode);

    expect(onUpdate).not.toHaveBeenCalled();
  });
});

describe("share expiration helpers", () => {
  it("round-trips a local datetime value through the ISO conversion", () => {
    const value = "2030-01-02T03:04";

    expect(toDateTimeLocalValue(new Date(value).toISOString())).toBe(value);
  });
});
