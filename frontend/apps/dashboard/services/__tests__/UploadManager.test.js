import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { API_V1_FSNODE_TOUCH } from "../../constants/endpoints";
import { DashboardFsNodeList } from "../DashboardFsNodeList";
import { UploadManager, handleBeforeUnload } from "../UploadManager";

const PARENT_ID = "11111111-1111-1111-1111-111111111111";
const OTHER_PARENT_ID = "22222222-2222-2222-2222-222222222222";
const NODE_ID = "33333333-3333-3333-3333-333333333333";

const createFile = (name, size) => ({ name, size });

const touchResponse = (name, id = NODE_ID) => ({
  id,
  parent_id: PARENT_ID,
  name,
  type: "file",
  upload_url: `/upload/${id}`,
});

const requestError = (code, response = null) => Object.assign(
  new Error(`Request failed with ${code}`),
  { code, response },
);

const conflictError = (name) => requestError(409, {
  error_id: "FsNodeExistsError",
  description: "Target object already exists.",
  detail: `File named "${name}" already exists`,
  existing_node_id: "44444444-4444-4444-4444-444444444444",
  existing_type: "file",
});

const waitForStatus = (job, status) => vi.waitFor(() => {
  expect(job.status).toBe(status);
});

describe("UploadManager", () => {
  beforeEach(() => {
    UploadManager.reset();
    DashboardFsNodeList.current = { id: PARENT_ID, sorting: "default" };
    DashboardFsNodeList.ancestors = [];
    DashboardFsNodeList.elements = [];
  });

  afterEach(() => {
    vi.restoreAllMocks();
    UploadManager.reset();
  });

  it("uploads files sequentially with touch followed by content", async () => {
    const request = vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        const id = options.body.name === "a.txt"
          ? NODE_ID
          : "55555555-5555-5555-5555-555555555555";
        return Promise.resolve(touchResponse(options.body.name, id));
      }
      return Promise.resolve({
        id: url.split("/").pop(),
        name: "file.txt",
        type: "file",
      });
    });

    UploadManager.enqueueFiles([
      createFile("a.txt", 100),
      createFile("b.txt", 100),
    ], PARENT_ID);

    await vi.waitFor(() => {
      expect(UploadManager.status).toBe("done");
    });

    expect(request.mock.calls.map(([url]) => url)).toEqual([
      API_V1_FSNODE_TOUCH,
      `/upload/${NODE_ID}`,
      API_V1_FSNODE_TOUCH,
      "/upload/55555555-5555-5555-5555-555555555555",
    ]);
    expect(UploadManager.percent).toBe(100);
    expect(DashboardFsNodeList.elements).toHaveLength(2);
  });

  it("pauses on a conflict and replaces the existing file", async () => {
    const request = vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        if (options.body.name === "a.txt" && !options.body.replace) {
          return Promise.reject(conflictError("a.txt"));
        }
        return Promise.resolve(touchResponse(options.body.name));
      }
      return Promise.resolve({ id: NODE_ID, name: "a.txt", type: "file" });
    });

    UploadManager.enqueueFiles([
      createFile("a.txt", 100),
      createFile("b.txt", 100),
    ], PARENT_ID);

    const [first, second] = UploadManager.jobs;
    await waitForStatus(first, "conflict");

    expect(UploadManager.firstError).toBe(first);
    expect(UploadManager.status).toBe("failed");
    expect(second.status).toBe("queued");
    expect(request).toHaveBeenCalledTimes(1);

    UploadManager.replace(first);

    await vi.waitFor(() => {
      expect(UploadManager.status).toBe("done");
    });

    const [, secondCall] = request.mock.calls;
    const [secondUrl, secondOptions] = secondCall;
    expect(secondUrl).toBe(API_V1_FSNODE_TOUCH);
    expect(secondOptions.body).toEqual({
      parent_id: PARENT_ID,
      name: "a.txt",
      replace: true,
    });
    expect(UploadManager.jobs.every((job) => job.status === "done")).toBe(true);
  });

  it("keeps the existing share when replacing a file", async () => {
    const share = { id: "share-1", url: "/s/token", expires_at: null };
    DashboardFsNodeList.elements = [
      new DashboardFsNodeList.FsNodeCls({
        id: NODE_ID,
        parent_id: PARENT_ID,
        name: "a.txt",
        type: "file",
        share,
      }),
    ];
    vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        if (!options.body.replace) {
          return Promise.reject(conflictError("a.txt"));
        }
        return Promise.resolve(touchResponse("a.txt"));
      }
      return Promise.resolve({ id: NODE_ID, name: "a.txt", type: "file" });
    });

    UploadManager.enqueueFiles([createFile("a.txt", 100)], PARENT_ID);
    const [job] = UploadManager.jobs;

    await waitForStatus(job, "conflict");
    UploadManager.replace(job);

    await vi.waitFor(() => {
      expect(UploadManager.status).toBe("done");
    });

    expect(DashboardFsNodeList.elements).toHaveLength(1);
    expect(DashboardFsNodeList.elements[0].share).toEqual(share);
    expect(job.node.share).toEqual(share);
  });

  it("retries a failed content upload with the same upload URL", async () => {
    let uploadAttempts = 0;
    const request = vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        return Promise.resolve(touchResponse(options.body.name));
      }
      uploadAttempts += 1;
      if (uploadAttempts === 1) {
        return Promise.reject(requestError(0));
      }
      return Promise.resolve({ id: NODE_ID, name: "a.txt", type: "file" });
    });

    UploadManager.enqueueFiles([createFile("a.txt", 100)], PARENT_ID);
    const [job] = UploadManager.jobs;

    await waitForStatus(job, "error");
    expect(job.error.code).toBe(0);
    expect(job.error.retryable).toBe(true);

    UploadManager.retry(job);

    await vi.waitFor(() => {
      expect(UploadManager.status).toBe("done");
    });

    const touchCalls = request.mock.calls.filter(
      ([url]) => url === API_V1_FSNODE_TOUCH,
    );
    const uploadCalls = request.mock.calls.filter(
      ([url]) => url !== API_V1_FSNODE_TOUCH,
    );
    expect(touchCalls).toHaveLength(1);
    expect(uploadCalls).toHaveLength(2);
    expect(uploadCalls[0][0]).toBe(uploadCalls[1][0]);
  });

  it("deletes a placeholder node when the user skips a failed file", async () => {
    const request = vi.spyOn(m, "request").mockImplementation((url) => {
      if (url === API_V1_FSNODE_TOUCH) {
        return Promise.resolve(touchResponse("a.txt"));
      }
      if (url.startsWith("/api/v1/fs-node/")) {
        return Promise.resolve({});
      }
      return Promise.reject(requestError(500, {}));
    });

    UploadManager.enqueueFiles([createFile("a.txt", 100)], PARENT_ID);
    const [job] = UploadManager.jobs;

    await waitForStatus(job, "error");
    await UploadManager.skip(job);

    expect(UploadManager.jobs).toHaveLength(0);
    expect(DashboardFsNodeList.elements).toHaveLength(0);
    expect(request).toHaveBeenCalledWith(
      `/api/v1/fs-node/${NODE_ID}/`,
      { method: "DELETE" },
    );
  });

  it("aborts active uploads and deletes their placeholder nodes", async () => {
    const xhr = { abort: vi.fn(), upload: {} };
    const request = vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        return Promise.resolve(touchResponse("a.txt"));
      }
      if (url.startsWith("/api/v1/fs-node/")) {
        return Promise.resolve({});
      }
      options.config(xhr);
      return new Promise(() => {
        // Pending forever; cancelAll aborts it before it resolves.
      });
    });

    UploadManager.enqueueFiles([createFile("a.txt", 100)], PARENT_ID);
    const [job] = UploadManager.jobs;

    await waitForStatus(job, "uploading");
    UploadManager.cancelAll();

    await vi.waitFor(() => {
      expect(request).toHaveBeenCalledWith(
        `/api/v1/fs-node/${NODE_ID}/`,
        { method: "DELETE" },
      );
    });

    expect(xhr.abort).toHaveBeenCalled();
    expect(job.status).toBe("canceled");
    expect(UploadManager.status).toBe("stopped");
    expect(DashboardFsNodeList.elements).toHaveLength(0);
  });

  it("tracks upload progress", async () => {
    const xhr = { abort: vi.fn(), upload: {} };
    let resolveUpload = null;
    vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        return Promise.resolve(touchResponse("a.txt"));
      }
      options.config(xhr);
      return new Promise((resolve) => {
        resolveUpload = resolve;
      });
    });

    UploadManager.enqueueFiles([createFile("a.txt", 100)], PARENT_ID);
    const [job] = UploadManager.jobs;

    await waitForStatus(job, "uploading");
    xhr.upload.onprogress({ loaded: 50 });

    expect(UploadManager.percent).toBe(50);

    resolveUpload({ id: NODE_ID, name: "a.txt", type: "file" });

    await waitForStatus(job, "done");
    expect(UploadManager.percent).toBe(100);
  });

  it("reports byte-weighted progress for the whole queue", async () => {
    const xhr = { abort: vi.fn(), upload: {} };
    let uploads = 0;
    let resolveFirst = null;
    vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        return Promise.resolve(touchResponse(options.body.name));
      }
      options.config(xhr);
      uploads += 1;
      if (uploads === 1) {
        return new Promise((resolve) => {
          resolveFirst = resolve;
        });
      }
      return new Promise(() => {
        // Keep the second upload in progress for the assertion.
      });
    });

    UploadManager.enqueueFiles([
      createFile("a.bin", 100),
      createFile("b.bin", 300),
    ], PARENT_ID);

    await vi.waitFor(() => {
      expect(uploads).toBe(1);
    });

    xhr.upload.onprogress({ loaded: 100 });
    expect(UploadManager.percent).toBe(25);

    resolveFirst({ id: NODE_ID, name: "a.bin", type: "file" });
    await vi.waitFor(() => {
      expect(uploads).toBe(2);
    });

    expect(UploadManager.completedCount).toBe(1);
    expect(UploadManager.percent).toBe(25);

    xhr.upload.onprogress({ loaded: 150 });
    expect(UploadManager.percent).toBe(63);
  });

  it("does not add nodes to a directory the user already left", async () => {
    vi.spyOn(m, "request").mockImplementation((url, options) => {
      if (url === API_V1_FSNODE_TOUCH) {
        return Promise.resolve(touchResponse(options.body.name));
      }
      return Promise.resolve({ id: NODE_ID, name: "a.txt", type: "file" });
    });
    DashboardFsNodeList.current = { id: OTHER_PARENT_ID, sorting: "default" };

    UploadManager.enqueueFiles([createFile("a.txt", 100)], PARENT_ID);

    await vi.waitFor(() => {
      expect(UploadManager.status).toBe("done");
    });

    expect(DashboardFsNodeList.elements).toHaveLength(0);
  });

  it("asks for confirmation before leaving while uploads are pending", () => {
    UploadManager.jobs = [{ status: "uploading" }];
    const event = { preventDefault: vi.fn() };

    handleBeforeUnload(event);

    expect(event.preventDefault).toHaveBeenCalledTimes(1);
    expect(event.returnValue).toBe("");
  });

  it("does not block leaving when the queue is finished", () => {
    UploadManager.jobs = [{ status: "done" }];
    const event = { preventDefault: vi.fn() };

    handleBeforeUnload(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(event.returnValue).toBeUndefined();
  });

  it("does not block leaving after canceling every upload", () => {
    UploadManager.jobs = [{ status: "canceled" }];
    const event = { preventDefault: vi.fn() };

    handleBeforeUnload(event);

    expect(event.preventDefault).not.toHaveBeenCalled();
  });
});
