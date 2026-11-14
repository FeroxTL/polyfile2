import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { API_V1_FSNODE, API_V1_FSNODE_BY_ID } from "../constants/endpoints";
import { DashboardFsNodeList } from "../services/DashboardFsNodeList";
import { loadDashboardRoute } from "../route";

const NODE_ID = "11111111-1111-1111-1111-111111111111";

describe("loadDashboardRoute()", () => {
  beforeEach(() => {
    vi.spyOn(DashboardFsNodeList, "consumePendingPath").mockReturnValue(false);
    vi.spyOn(DashboardFsNodeList, "load").mockResolvedValue();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("skips the load when the route path is already loading by UUID", () => {
    DashboardFsNodeList.consumePendingPath.mockReturnValue(true);

    loadDashboardRoute("/folder");

    expect(DashboardFsNodeList.load).not.toHaveBeenCalled();
  });

  it("loads the bootstrapped node by UUID when the path matches", () => {
    loadDashboardRoute("/folder/", { path: "/folder", node_id: NODE_ID });

    expect(DashboardFsNodeList.load).toHaveBeenCalledWith(
      m.buildPathname(API_V1_FSNODE_BY_ID, { id: NODE_ID }),
      {},
    );
  });

  it("falls back to the path lookup when the bootstrap is for another path", () => {
    loadDashboardRoute("/other", { path: "/folder", node_id: NODE_ID });

    expect(DashboardFsNodeList.load).toHaveBeenCalledWith(
      API_V1_FSNODE,
      { path: "/other" },
    );
  });

  it("falls back to the path lookup without a bootstrap", () => {
    loadDashboardRoute("/folder");

    expect(DashboardFsNodeList.load).toHaveBeenCalledWith(
      API_V1_FSNODE,
      { path: "/folder" },
    );
  });
});
