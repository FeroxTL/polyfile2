import { afterEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { ARCHIVE_STATUS } from "../../models/ArchiveJob";
import {
  ArchiveDownloadService,
  describeArchiveError,
} from "../ArchiveDownloadService";

describe("ArchiveDownloadService", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("starts a job with the JSON format", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      job_id: "job-1",
      status: ARCHIVE_STATUS.PENDING,
      status_url: "/download/jobs/job-1/status/",
    });

    const job = await ArchiveDownloadService.start("/download/node/");

    expect(request).toHaveBeenCalledWith("/download/node/", {
      method: "GET",
      params: { format: "json" },
      headers: { Accept: "application/json" },
    });
    expect(job.job_id).toBe("job-1");
    expect(job.status).toBe(ARCHIVE_STATUS.PENDING);
  });

  it("polls a status URL", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue({
      status: ARCHIVE_STATUS.RUNNING,
      processed_files: 1,
      total_files: 2,
    });

    const job = await ArchiveDownloadService.status("/download/jobs/job-1/status/");

    expect(request).toHaveBeenCalledWith("/download/jobs/job-1/status/", {
      method: "GET",
      headers: { Accept: "application/json" },
    });
    expect(job.progress_percent).toBe(50);
  });

  it("rejects a missing download URL", async () => {
    await expect(ArchiveDownloadService.start("")).rejects.toThrow(
      "Archive download URL is missing.",
    );
  });

  it("rejects a missing status URL", async () => {
    await expect(ArchiveDownloadService.status("")).rejects.toThrow(
      "Archive status URL is missing.",
    );
  });

  it("checks a ready archive file with HEAD", async () => {
    const request = vi.spyOn(m, "request").mockResolvedValue(null);

    await expect(
      ArchiveDownloadService.checkFile("/download/jobs/job-1/file/"),
    ).resolves.toBe(true);

    expect(request).toHaveBeenCalledWith("/download/jobs/job-1/file/", {
      method: "HEAD",
      headers: { Accept: "application/zip" },
    });
  });

  it("rejects a missing archive file URL", async () => {
    await expect(ArchiveDownloadService.checkFile("")).rejects.toThrow(
      "Archive file URL is missing.",
    );
  });
});

describe("describeArchiveError", () => {
  it("explains an expired or deleted archive", () => {
    expect(describeArchiveError({ code: 410 })).toContain("no longer available");
  });

  it("explains a missing archive without a response body", () => {
    expect(describeArchiveError({ code: 404 })).toContain("no longer available");
  });

  it("uses the backend detail", () => {
    expect(describeArchiveError({
      code: 409,
      response: { detail: "Archive is already running." },
    })).toBe("Archive is already running.");
  });

  it("formats validation details", () => {
    expect(describeArchiveError({
      code: 400,
      response: { detail: ["first", "second"] },
    })).toBe("first; second");
  });

  it("falls back to the transport message", () => {
    expect(describeArchiveError({ code: 0, message: "Network down" }))
      .toBe("Network down");
  });

  it("has a generic fallback", () => {
    expect(describeArchiveError(null)).toContain("Could not prepare");
  });
});
