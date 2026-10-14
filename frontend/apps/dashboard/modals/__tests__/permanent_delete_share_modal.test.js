import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../bootstrap/modal", () => ({
  Modal: {},
  closeModal: vi.fn(),
  showModal: vi.fn(),
}));

import { closeModal, showModal } from "../../bootstrap/modal";
import {
  PermanentDeleteShareModal,
  showPermanentDeleteShareModal,
} from "../permanent_delete_share_modal";

const createVnode = (onConfirm = vi.fn().mockResolvedValue()) => ({
  attrs: {
    modalId: ["modal"],
    share: {
      id: "4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10",
      root_fs_node: { name: "report.txt", type: "file" },
    },
    onConfirm,
  },
  state: {
    loading: false,
    error: null,
  },
});

describe("PermanentDeleteShareModal.confirm()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.mocked(closeModal).mockClear();
  });

  it("confirms permanent deletion and closes the modal", async () => {
    const onConfirm = vi.fn().mockResolvedValue();
    const vnode = createVnode(onConfirm);

    PermanentDeleteShareModal.confirm(vnode);

    await vi.waitFor(() => {
      expect(closeModal).toHaveBeenCalledWith(vnode.attrs.modalId);
    });
    expect(onConfirm).toHaveBeenCalledWith(vnode.attrs.share);
    expect(vnode.state.loading).toBe(false);
    expect(vnode.state.error).toBeNull();
  });

  it("shows an error and keeps the modal open when deletion fails", async () => {
    const vnode = createVnode(
      vi.fn().mockRejectedValue({ response: { detail: "Share does not exist." } }),
    );

    PermanentDeleteShareModal.confirm(vnode);

    await vi.waitFor(() => {
      expect(vnode.state.error).toBe("Share does not exist.");
    });
    expect(closeModal).not.toHaveBeenCalled();
    expect(vnode.state.loading).toBe(false);
  });

  it("ignores clicks while a delete request is running", () => {
    const onConfirm = vi.fn();
    const vnode = createVnode(onConfirm);
    vnode.state.loading = true;

    PermanentDeleteShareModal.confirm(vnode);

    expect(onConfirm).not.toHaveBeenCalled();
  });
});

describe("showPermanentDeleteShareModal()", () => {
  afterEach(() => {
    vi.mocked(showModal).mockClear();
  });

  it("opens the modal with the share and confirmation handler", () => {
    const attrs = {
      share: { id: "4c5e1f46-8e9a-4b7a-9e64-6d3f1c2a7b10" },
      onConfirm: vi.fn(),
    };

    showPermanentDeleteShareModal(attrs);

    expect(showModal).toHaveBeenCalledWith(PermanentDeleteShareModal, attrs);
  });
});
