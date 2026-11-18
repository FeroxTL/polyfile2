// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../bootstrap/modal", () => ({
  showModal: vi.fn(),
  closeModal: vi.fn(),
  Modal: { modalHeader: {}, view: () => null },
  ModalsAndBackdrop: { view: () => null },
}));

import { showModal } from "../bootstrap/modal";
import { openMoveModal } from "../dashboard";
import { MoveFsNodeModal } from "../modals/MoveFsNodeModal";

afterEach(() => {
  vi.mocked(showModal).mockClear();
});

describe("openMoveModal()", () => {
  it("opens the move modal with the selected node", () => {
    const fsNode = { id: "11111111-1111-1111-1111-111111111111" };

    openMoveModal(fsNode);

    expect(showModal).toHaveBeenCalledWith(MoveFsNodeModal, { fsNode });
  });
});
