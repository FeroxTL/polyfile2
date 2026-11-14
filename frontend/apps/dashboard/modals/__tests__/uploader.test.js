import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import { uploadFile } from "../uploader";

const PARENT_ID = "11111111-1111-1111-1111-111111111111";

const createEvent = (fileNames) => ({
  target: {
    files: fileNames.map((name) => ({ name })),
  },
});

describe("uploader.uploadFile()", () => {
  beforeEach(() => {
    DashboardFsNodeList.current = null;
    DashboardFsNodeList.elements = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("creates the node by parent id and file name, then uploads the content", async () => {
    const request = vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === "/api/v1/fs-node/touch") {
        return Promise.resolve({
          id: "22222222-2222-2222-2222-222222222222",
          name: options.body.name,
          type: "file",
          upload_url: "/upload/some-token",
        });
      }
      return Promise.resolve({});
    });
    DashboardFsNodeList.current = { id: PARENT_ID };

    uploadFile(createEvent(["report.pdf"]));
    await vi.waitFor(() => {
      expect(request).toHaveBeenCalledTimes(2);
    });

    expect(request).toHaveBeenNthCalledWith(1, "/api/v1/fs-node/touch", {
      method: "POST",
      body: { parent_id: PARENT_ID, name: "report.pdf" },
    });
    expect(request).toHaveBeenNthCalledWith(2, "/upload/some-token", expect.objectContaining({
      method: "POST",
    }));
    expect(DashboardFsNodeList.elements).toHaveLength(1);
  });

  it("creates the node in the virtual root when there is no current id", async () => {
    const request = vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === "/api/v1/fs-node/touch") {
        return Promise.resolve({
          id: "22222222-2222-2222-2222-222222222222",
          name: options.body.name,
          type: "file",
          upload_url: "/upload/some-token",
        });
      }
      return Promise.resolve({});
    });
    DashboardFsNodeList.current = { id: null };

    uploadFile(createEvent(["report.pdf"]));
    await vi.waitFor(() => {
      expect(request).toHaveBeenCalledTimes(2);
    });

    expect(request).toHaveBeenNthCalledWith(1, "/api/v1/fs-node/touch", {
      method: "POST",
      body: { parent_id: null, name: "report.pdf" },
    });
  });
});
