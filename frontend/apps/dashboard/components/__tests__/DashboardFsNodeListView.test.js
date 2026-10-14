import { describe, expect, it, vi } from "vitest";

import { DashboardFsNodeListView } from "../DashboardFsNodeListView";

const createListView = () => new DashboardFsNodeListView({
  attrs: {
    fsnodeList: {
      current: { path: "/" },
      elements: [],
      selectFsNode: vi.fn(),
    },
    navigationHandler: vi.fn(),
  },
});

const renderShareAction = ({
  share = { id: "token", url: "https://example.com/s/token/" },
  onShareClick = vi.fn(),
} = {}) => {
  const fsNode = {
    name: "file.txt",
    type: "file",
    share,
  };
  const vnode = { attrs: { onShareClick } };
  const attrs = createListView().childViewAttrs(vnode, fsNode);

  return {
    action: attrs.renderActions(fsNode),
    fsNode,
    onShareClick,
  };
};

describe("DashboardFsNodeListView share action", () => {
  it("renders a share button for a shared node", () => {
    const { action } = renderShareAction();

    expect(action).toBeTruthy();
    expect(action.attrs.title).toBe("Open share link");
  });

  it("does not render a share button when there is no active share", () => {
    const { action } = renderShareAction({ share: null });

    expect(action).toBeNull();
  });

  it("does not render a share button without an onShareClick handler", () => {
    const { action } = renderShareAction({ onShareClick: null });

    expect(action).toBeNull();
  });

  it("opens the share modal without selecting or navigating the node", () => {
    const { action, fsNode, onShareClick } = renderShareAction();
    const event = {
      preventDefault: vi.fn(),
      stopPropagation: vi.fn(),
    };

    action.attrs.onclick(event);

    expect(onShareClick).toHaveBeenCalledWith(fsNode);
    expect(event.preventDefault).toHaveBeenCalled();
    expect(event.stopPropagation).toHaveBeenCalled();
  });
});
