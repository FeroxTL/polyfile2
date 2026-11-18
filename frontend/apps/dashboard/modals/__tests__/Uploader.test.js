import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/UploadManager", () => ({
  UploadManager: {
    enqueueFiles: vi.fn(),
  },
}));

import { UploadManager } from "../../services/UploadManager";
import { DashboardFsNodeList } from "../../services/DashboardFsNodeList";
import { uploadFile } from "../Uploader";

const PARENT_ID = "11111111-1111-1111-1111-111111111111";

const createEvent = (fileNames) => ({
  target: {
    files: fileNames.map((name) => ({ name })),
    value: "selected-file",
  },
});

describe("Uploader.uploadFile()", () => {
  beforeEach(() => {
    DashboardFsNodeList.current = { id: PARENT_ID };
    vi.mocked(UploadManager.enqueueFiles).mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("hands the selected files to the upload queue with the current parent", () => {
    const event = createEvent(["report.pdf"]);

    uploadFile(event);

    expect(UploadManager.enqueueFiles).toHaveBeenCalledWith(
      [{ name: "report.pdf" }],
      PARENT_ID,
    );
    expect(event.target.value).toBe("");
  });

  it("captures the virtual root when there is no current node", () => {
    DashboardFsNodeList.current = null;
    const event = createEvent(["report.pdf"]);

    uploadFile(event);

    expect(UploadManager.enqueueFiles).toHaveBeenCalledWith(
      [{ name: "report.pdf" }],
      null,
    );
  });

  it("does nothing when the input has no files", () => {
    const event = createEvent([]);

    uploadFile(event);

    expect(UploadManager.enqueueFiles).not.toHaveBeenCalled();
  });
});
