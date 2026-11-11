import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ArchiveJob, ARCHIVE_STATUS } from "../../models/ArchiveJob";
import { ArchiveDownloadService } from "../../services/ArchiveDownloadService";
import { ArchiveDownloadModal } from "../ArchiveDownloadModal";

const POLL_DELAY_MS = 1000;
const LONG_DELAY_MS = 5000;

const makeVnode = () => ({
  attrs: {
    downloadUrl: "/download/node/",
    modalId: ["modal", {}],
  },
  state: {},
});

const flushPromises = async () => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};

const openModal = async () => {
  const vnode = makeVnode();
  ArchiveDownloadModal.oninit(vnode);
  await flushPromises();
  return vnode;
};

describe("ArchiveDownloadModal", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("starts a job and schedules the first poll", async () => {
    const start = vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );

    const vnode = await openModal();

    expect(start).toHaveBeenCalledWith("/download/node/");
    expect(vnode.state.job.status).toBe(ARCHIVE_STATUS.PENDING);
    expect(vnode.state.timer).not.toBeNull();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("polls the status URL and stops after a ready job", async () => {
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );
    const status = vi.spyOn(ArchiveDownloadService, "status").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.READY,
        file_url: "/download/jobs/1/file/",
      }),
    );
    const checkFile = vi
      .spyOn(ArchiveDownloadService, "checkFile")
      .mockResolvedValue(true);

    const vnode = await openModal();
    await vi.advanceTimersByTimeAsync(POLL_DELAY_MS);
    await flushPromises();

    expect(status).toHaveBeenCalledWith("/download/jobs/1/status/");
    expect(checkFile).toHaveBeenCalledWith("/download/jobs/1/file/");
    expect(vnode.state.job.is_ready).toBe(true);
    expect(vnode.state.timer).toBeNull();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("navigates to the archive after a successful file check", async () => {
    const assign = vi.fn();
    vi.stubGlobal("window", { location: { assign } });
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );
    vi.spyOn(ArchiveDownloadService, "status").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.READY,
        file_url: "/download/jobs/1/file/",
      }),
    );
    vi.spyOn(ArchiveDownloadService, "checkFile").mockResolvedValue(true);

    const vnode = await openModal();
    await vi.advanceTimersByTimeAsync(POLL_DELAY_MS);
    await flushPromises();

    expect(assign).toHaveBeenCalledWith("/download/jobs/1/file/");
    expect(vnode.state.downloaded).toBe(true);
    expect(vnode.state.error).toBe("");

    ArchiveDownloadModal.onremove(vnode);
  });

  it("keeps a deleted archive error inside the modal", async () => {
    const assign = vi.fn();
    vi.stubGlobal("window", { location: { assign } });
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );
    vi.spyOn(ArchiveDownloadService, "status").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.READY,
        file_url: "/download/jobs/1/file/",
      }),
    );
    vi.spyOn(ArchiveDownloadService, "checkFile").mockRejectedValue({
      code: 410,
    });

    const vnode = await openModal();
    await vi.advanceTimersByTimeAsync(POLL_DELAY_MS);
    await flushPromises();

    expect(vnode.state.error).toContain("no longer available");
    expect(vnode.state.downloaded).toBe(false);
    expect(vnode.state.timer).toBeNull();
    expect(assign).not.toHaveBeenCalled();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("does not navigate when the file check fails with 404", async () => {
    const assign = vi.fn();
    vi.stubGlobal("window", { location: { assign } });
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );
    vi.spyOn(ArchiveDownloadService, "status").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.READY,
        file_url: "/download/jobs/1/file/",
      }),
    );
    vi.spyOn(ArchiveDownloadService, "checkFile").mockRejectedValue({
      code: 404,
    });

    const vnode = await openModal();
    await vi.advanceTimersByTimeAsync(POLL_DELAY_MS);
    await flushPromises();

    expect(vnode.state.error).toContain("no longer available");
    expect(assign).not.toHaveBeenCalled();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("shows the backend error for a failed job", async () => {
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.FAILED,
        last_error: "Disk is full.",
      }),
    );

    const vnode = await openModal();

    expect(vnode.state.error).toBe("Disk is full.");
    expect(vnode.state.timer).toBeNull();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("stops polling when the status endpoint reports a gone archive", async () => {
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );
    vi.spyOn(ArchiveDownloadService, "status").mockRejectedValue({ code: 410 });

    const vnode = await openModal();
    await vi.advanceTimersByTimeAsync(POLL_DELAY_MS);
    await flushPromises();

    expect(vnode.state.error).toContain("no longer available");
    expect(vnode.state.timer).toBeNull();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("keeps polling after a transient status error", async () => {
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );
    vi.spyOn(ArchiveDownloadService, "status").mockRejectedValue({
      code: 0,
      message: "Network down",
    });

    const vnode = await openModal();
    await vi.advanceTimersByTimeAsync(POLL_DELAY_MS);
    await flushPromises();

    expect(vnode.state.error).toBe("Network down");
    expect(vnode.state.timer).not.toBeNull();

    ArchiveDownloadModal.onremove(vnode);
  });

  it("creates a new job when the user retries", async () => {
    const start = vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.FAILED,
        last_error: "Disk is full.",
      }),
    );

    const vnode = await openModal();
    ArchiveDownloadModal.start(vnode);
    await flushPromises();

    expect(start).toHaveBeenCalledTimes(2);

    ArchiveDownloadModal.onremove(vnode);
  });

  it("does not poll after the modal is removed", async () => {
    const status = vi.spyOn(ArchiveDownloadService, "status");
    vi.spyOn(ArchiveDownloadService, "start").mockResolvedValue(
      new ArchiveJob({
        status: ARCHIVE_STATUS.PENDING,
        status_url: "/download/jobs/1/status/",
        retry_after: 1,
      }),
    );

    const vnode = await openModal();
    ArchiveDownloadModal.onremove(vnode);
    await vi.advanceTimersByTimeAsync(LONG_DELAY_MS);

    expect(status).not.toHaveBeenCalled();
  });
});
