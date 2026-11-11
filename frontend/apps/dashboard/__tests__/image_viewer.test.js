// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";

import ImageViewerModal from "../image_viewer";

const createFsNode = (name = "image.png") => ({
  name,
  type: "file",
  mime_type: "image/png",
  download_url: `/download/${name}`,
});

const createVnode = (imageCount = 1, currentIndex = 0) => {
  const items = Array.from({ length: imageCount }, (_, i) => createFsNode(`img${i}.png`));
  const vnode = { attrs: { currentImg: items[currentIndex], items }, state: {} };

  ImageViewerModal.oninit(vnode);

  // Provide real DOM elements so slide/pointer helpers can measure sizes.
  vnode.state.itemsEl = items.map(() => {
    const container = document.createElement("div");
    const img = document.createElement("img");
    container.appendChild(img);
    Object.defineProperty(container, "offsetHeight", { value: 1000, configurable: true });
    Object.defineProperty(container, "offsetWidth", { value: 1000, configurable: true });
    Object.defineProperty(img, "offsetHeight", { value: 500, configurable: true });
    Object.defineProperty(img, "offsetWidth", { value: 500, configurable: true });
    return container;
  });

  return vnode;
};

const DRAG_PAST_SLIDE_OFFSET = 50;

const triggerPointerUpWithDrag = (vnode, moveX) => {
  const event = { pointerId: 1, clientX: 0, clientY: 0 };
  vnode.state.evCache = [event];
  vnode.state.currentMove.x = moveX;
  ImageViewerModal.pointerUpEvent(vnode, event);
};

describe("ImageViewerModal", () => {
  beforeEach(() => {
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
  });

  describe("slide", () => {
    it("returns false and keeps the current image when there is only one image", () => {
      const vnode = createVnode(1);

      const result = ImageViewerModal.slide(vnode, true);

      expect(result).toBe(false);
      expect(vnode.state.currentImg.fs_node.name).toBe("img0.png");
      expect(vnode.state.isSliding).toBe(false);
    });

    it("returns true and starts sliding when a next image exists", () => {
      const vnode = createVnode(2, 0);

      const result = ImageViewerModal.slide(vnode, true);

      expect(result).toBe(true);
      expect(vnode.state.isSliding).toBe(true);
      expect(vnode.state.currentMove.y).toBe(0);
      expect(vnode.state.currentScale).toBe(1);
      expect(vnode.state.itemsEl[1].classList.contains("carousel-item-next")).toBe(true);
      expect(vnode.state.itemsEl[1].classList.contains("carousel-item-start")).toBe(true);
    });
  });

  describe("pointerUpEvent", () => {
    it("resets horizontal move when a single image is dragged past the slide offset", () => {
      const vnode = createVnode(1);

      triggerPointerUpWithDrag(vnode, DRAG_PAST_SLIDE_OFFSET);

      expect(vnode.state.currentMove.x).toBe(0);
    });

    it("keeps horizontal move when multiple images are dragged past the slide offset", () => {
      const vnode = createVnode(2);

      triggerPointerUpWithDrag(vnode, DRAG_PAST_SLIDE_OFFSET);

      expect(vnode.state.currentMove.x).toBe(DRAG_PAST_SLIDE_OFFSET);
      expect(vnode.state.isSliding).toBe(true);
    });
  });
});
