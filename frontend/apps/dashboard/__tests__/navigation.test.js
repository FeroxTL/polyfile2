// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { FILES_DASHBOARD_URL } from "../constants/endpoints";
import { DashboardFsNodeList } from "../services/DashboardFsNodeList";
import {
  dashboardBreadcrumbHandler,
  dashboardNavigationHandler,
} from "../dashboard";

const NODE_ID = "11111111-1111-1111-1111-111111111111";

describe("dashboardNavigationHandler()", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("preloads the directory by UUID and keeps the path-based URL", () => {
    vi.spyOn(DashboardFsNodeList, "loadByNodeId").mockResolvedValue();
    vi.spyOn(m.route, "set").mockReturnValue();

    dashboardNavigationHandler("/root", "sub", { id: NODE_ID, name: "sub" });

    expect(DashboardFsNodeList.loadByNodeId).toHaveBeenCalledWith(NODE_ID, "/root/sub");
    expect(m.route.set).toHaveBeenCalledWith(FILES_DASHBOARD_URL, { path: "/root/sub" });
  });

  it("navigates by path when the node has no UUID", () => {
    vi.spyOn(DashboardFsNodeList, "loadByNodeId").mockResolvedValue();
    vi.spyOn(m.route, "set").mockReturnValue();

    dashboardNavigationHandler("/", "new", {});

    expect(DashboardFsNodeList.loadByNodeId).not.toHaveBeenCalled();
    expect(m.route.set).toHaveBeenCalledWith(FILES_DASHBOARD_URL, { path: "/new" });
  });

  it("preloads a breadcrumb target by UUID without navigating itself", () => {
    vi.spyOn(DashboardFsNodeList, "loadByNodeId").mockResolvedValue();
    vi.spyOn(m.route, "set").mockReturnValue();

    dashboardBreadcrumbHandler({ id: NODE_ID, name: "root" }, "root/sub");

    expect(DashboardFsNodeList.loadByNodeId).toHaveBeenCalledWith(NODE_ID, "/root/sub");
    // m.route.Link performs the navigation after the preload is started.
    expect(m.route.set).not.toHaveBeenCalled();
  });
});
