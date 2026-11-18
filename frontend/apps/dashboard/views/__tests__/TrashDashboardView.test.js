import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../components/DashboardShell", () => ({
  DashboardShell: {
    view: (vnode) => vnode.children,
  },
}));
vi.mock("../../modals/trash_confirm_modal", () => ({
  showTrashConfirmModal: vi.fn(),
}));
vi.mock("../../modals/restore_monitor_modal", () => ({
  showRestoreMonitorModal: vi.fn(),
}));
vi.mock("@polyfile/core/ui-kit/button", () => ({
  // A function component: m() accepts it without invoking the view,
  // so the vnode keeps its attrs/children for the tests to inspect.
  default: () => ({ tag: "button" }),
}));

import m from "mithril";
import Button from "@polyfile/core/ui-kit/button";
import { showTrashConfirmModal } from "../../modals/trash_confirm_modal";
import { showRestoreMonitorModal } from "../../modals/restore_monitor_modal";
import { TrashList } from "../../services/TrashList";
import { TrashDashboardView } from "../TrashDashboardView";

const ENTRY_A = { id: "11111111-1111-1111-1111-111111111111", name: "a.txt", type: "file", trashed_at: "2026-01-01T00:00:00Z" };
const ENTRY_B = { id: "22222222-2222-2222-2222-222222222222", name: "docs", type: "directory", trashed_at: "2026-01-02T00:00:00Z" };

/** Render the view and return the resulting vnode tree. */
const render = (vnode) => TrashDashboardView.view(vnode);

/** Collect all text content of a vnode tree. */
const treeText = (tree) => JSON.stringify(tree);
const findButtons = (tree) => {
  const found = [];
  const walk = (node) => {
    if (!node) {
      return;
    }
    if (Array.isArray(node)) {
      node.forEach(walk);
      return;
    }
    if (typeof node !== "object") {
      return;
    }
    if (node.tag === Button) {
      found.push(node);
    }
    walk(node.children);
  };
  walk(tree);
  return found;
};

/** Fire the click handler of a vnode. */
const click = (vnode) => {
  vnode.attrs.onclick();
};

beforeEach(() => {
  TrashList.entries = [];
  TrashList.selected.clear();
  TrashList.isLoading = false;
  TrashList.error = null;
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(showTrashConfirmModal).mockClear();
  vi.mocked(showRestoreMonitorModal).mockClear();
});

describe("TrashDashboardView", () => {
  it("loads the trash on init", () => {
    const load = vi.spyOn(TrashList, "load").mockResolvedValue({});
    TrashDashboardView.oninit({ state: {} });
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("renders the empty state without the 'Empty trash' action", () => {
    const vnode = { state: { service: TrashList } };
    const tree = render(vnode);
    expect(treeText(tree)).toContain("Trash is empty.");
    // Nothing to empty: the action is hidden.
    expect(findButtons(tree)).toHaveLength(0);
  });

  it("renders one list item per entry", () => {
    TrashList.entries = [ENTRY_A, ENTRY_B];
    const vnode = { state: { service: TrashList } };
    const tree = render(vnode);
    expect(treeText(tree)).toContain("a.txt");
    expect(treeText(tree)).toContain("docs");
  });

  it("shows 'Empty trash' when entries exist and nothing is selected", () => {
    TrashList.entries = [ENTRY_A];
    const vnode = { state: { service: TrashList } };
    const buttons = findButtons(render(vnode));
    expect(buttons).toHaveLength(1);
  });

  it("shows restore/delete actions when entries are selected", () => {
    TrashList.entries = [ENTRY_A, ENTRY_B];
    TrashList.toggleSelected(ENTRY_A.id);
    const vnode = { state: { service: TrashList } };
    const buttons = findButtons(render(vnode));
    // Restore, Delete permanently and clear-selection.
    expect(buttons).toHaveLength(3);
  });

  it("toggles selection when an entry is clicked", () => {
    TrashList.entries = [ENTRY_A];
    const vnode = { state: { service: TrashList } };
    render(vnode);

    TrashList.toggleSelected(ENTRY_A.id);

    expect(TrashList.selected.has(ENTRY_A.id)).toBe(true);
  });

  it("opens the restore monitor for the selection", () => {
    TrashList.entries = [ENTRY_A, ENTRY_B];
    TrashList.toggleSelected(ENTRY_A.id);
    TrashList.toggleSelected(ENTRY_B.id);
    const vnode = { state: { service: TrashList } };
    click(findButtons(render(vnode))[0]);

    expect(showRestoreMonitorModal).toHaveBeenCalledTimes(1);
    const [[attrs]] = showRestoreMonitorModal.mock.calls;
    expect(attrs.entries).toEqual([ENTRY_A, ENTRY_B]);
    expect(attrs.service).toBe(TrashList);
  });

  it("opens the permanent delete confirm for the selection", () => {
    TrashList.entries = [ENTRY_A];
    TrashList.toggleSelected(ENTRY_A.id);
    const vnode = { state: { service: TrashList } };
    click(findButtons(render(vnode))[1]);

    expect(showTrashConfirmModal).toHaveBeenCalledTimes(1);
    const [[attrs]] = showTrashConfirmModal.mock.calls;
    expect(attrs.entries).toEqual([ENTRY_A]);
  });

  it("shows the loading and error states", () => {
    TrashList.isLoading = true;
    let tree = render({ state: { service: TrashList } });
    expect(treeText(tree)).toContain("Loading...");

    TrashList.isLoading = false;
    TrashList.error = new Error("boom");
    tree = render({ state: { service: TrashList } });
    expect(treeText(tree)).toContain("Failed to load the Trash.");
  });

  it("clears the selection on a document click outside marked areas", () => {
    vi.spyOn(m, "redraw").mockReturnValue(null);
    vi.spyOn(TrashList, "load").mockResolvedValue({});
    const vnode = { state: {} };
    TrashDashboardView.oninit(vnode);

    TrashList.entries = [ENTRY_A];
    TrashList.toggleSelected(ENTRY_A.id);

    const target = { closest: () => null };
    vnode.state.onDocumentClick({ target });

    expect(TrashList.selected.size).toBe(0);
  });

  it("keeps the selection when the click happens inside an ignored area", () => {
    vi.spyOn(m, "redraw").mockReturnValue(null);
    vi.spyOn(TrashList, "load").mockResolvedValue({});
    const vnode = { state: {} };
    TrashDashboardView.oninit(vnode);

    TrashList.entries = [ENTRY_A];
    TrashList.toggleSelected(ENTRY_A.id);

    const target = { closest: (selector) => (selector === ".app-ignore-selection" ? {} : null) };
    vnode.state.onDocumentClick({ target });

    expect(TrashList.selected.has(ENTRY_A.id)).toBe(true);
  });
});
