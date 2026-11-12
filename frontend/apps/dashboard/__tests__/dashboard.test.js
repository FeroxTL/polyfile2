// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";
import { DashboardFsNodeList } from "../services/DashboardFsNodeList";
import {API_V1_FSNODE} from "../constants/endpoints";

const rootResponse = {
  current: {
    id: null,
    parent_id: null,
    name: "",
    type: "directory",
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    size: 0,
    mime_type: "",
    md5: "",
    file: "",
    download_url: "",
    path: "/",
    share: null,
  },
  ancestors: [],
  children: [
    {
      id: "11111111-1111-1111-1111-111111111111",
      parent_id: null,
      name: "folder",
      type: "directory",
      created_at: "2026-01-01T00:00:00Z",
      modified_at: "2026-01-01T00:00:00Z",
      size: 0,
      mime_type: "",
      md5: "",
      file: "",
      download_url: "",
      path: "/folder",
      share: null,
    },
  ],
};

const folderResponse = {
  current: {
    id: "11111111-1111-1111-1111-111111111111",
    parent_id: null,
    name: "folder",
    type: "directory",
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    size: 0,
    mime_type: "",
    md5: "",
    file: "",
    download_url: "",
    path: "/folder",
    share: null,
  },
  ancestors: [],
  children: [],
};

const flushPromises = () => new Promise((resolve) => { setTimeout(resolve, 0); });

const setupMockRequest = () => {
  let requestCount = 0;
  vi.spyOn(m, "request").mockImplementation((url, options) => {
    requestCount += 1;
    const params = options?.params || {};
    const data = params.path === "/" ? rootResponse : folderResponse;
    return Promise.resolve(data);
  });
  return { getCount: () => requestCount };
};

describe("Dashboard loading guard", () => {
  beforeEach(() => {
    DashboardFsNodeList.current = null;
    DashboardFsNodeList.ancestors = [];
    DashboardFsNodeList.elements = [];
    DashboardFsNodeList.error = null;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the root directory", async () => {
    const { getCount } = setupMockRequest();

    DashboardFsNodeList.load(API_V1_FSNODE, { path: "" })
    await flushPromises();
    expect(getCount()).toBe(1);
  });

  it("loads a child directory exactly once when the route changes", async () => {
    const { getCount } = setupMockRequest();

    DashboardFsNodeList.load(API_V1_FSNODE, { path: "" })
    await flushPromises();
    expect(getCount()).toBe(1);

    DashboardFsNodeList.load(API_V1_FSNODE, { path: "folder" })
    await flushPromises();
    expect(getCount()).toBe(2);
    expect(DashboardFsNodeList.current?.name).toBe("folder");
  });
});
