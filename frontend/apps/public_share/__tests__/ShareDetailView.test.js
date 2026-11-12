// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";
import {loadData, ShareDetailView} from "../ShareDetailView";
import { ShareFsNodeList } from "../services/shareFsNodeList";

const rootResponse = {
  current: {
    id: "22222222-2222-2222-2222-222222222222",
    parent_id: null,
    name: "shared",
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
      id: "33333333-3333-3333-3333-333333333333",
      parent_id: "22222222-2222-2222-2222-222222222222",
      name: "child",
      type: "directory",
      created_at: "2026-01-01T00:00:00Z",
      modified_at: "2026-01-01T00:00:00Z",
      size: 0,
      mime_type: "",
      md5: "",
      file: "",
      download_url: "",
      path: "/child",
      share: null,
    },
  ],
};

const childResponse = {
  current: {
    id: "33333333-3333-3333-3333-333333333333",
    parent_id: "22222222-2222-2222-2222-222222222222",
    name: "child",
    type: "directory",
    created_at: "2026-01-01T00:00:00Z",
    modified_at: "2026-01-01T00:00:00Z",
    size: 0,
    mime_type: "",
    md5: "",
    file: "",
    download_url: "",
    path: "/child",
    share: null,
  },
  ancestors: [
    {
      id: "22222222-2222-2222-2222-222222222222",
      parent_id: null,
      name: "shared",
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
  ],
  children: [],
};

const flushPromises = () => new Promise((resolve) => { setTimeout(resolve, 0); });

const setupMockRequest = () => {
  let requestCount = 0;
  vi.spyOn(m, "request").mockImplementation((url) => {
    requestCount += 1;
    const urlString = typeof url === "string" ? url : url.url;
    const data = urlString.endsWith("/child") ? childResponse : rootResponse;
    return Promise.resolve(data);
  });
  return { getCount: () => requestCount };
};

describe("ShareDetailView", () => {
  beforeEach(() => {
    ShareFsNodeList.current = null;
    ShareFsNodeList.ancestors = [];
    ShareFsNodeList.elements = [];
    ShareFsNodeList.error = null;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the share root on init", async () => {
    const { getCount } = setupMockRequest();
    const attrs = { share_token: "token", path: "" };

    loadData(attrs);
    await flushPromises();

    expect(getCount()).toBe(1);
    expect(ShareFsNodeList.current?.name).toBe("shared");
  });

  it("loads a child directory based on path", async () => {
    const { getCount } = setupMockRequest();
    const attrs = { share_token: "token", path: "child" };

    loadData(attrs);
    await flushPromises();

    expect(getCount()).toBe(1);
    expect(ShareFsNodeList.current?.name).toBe("child");
  });

  it("ignores the Mithril key attr and uses path for requests", async () => {
    const { getCount } = setupMockRequest();
    const attrs = { share_token: "token", key: "token/ignored", path: "" };

    loadData(attrs);
    await flushPromises();

    expect(getCount()).toBe(1);
    expect(ShareFsNodeList.current?.name).toBe("shared");
  });
});
