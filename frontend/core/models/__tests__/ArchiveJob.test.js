import { describe, expect, it } from "vitest";

import { ARCHIVE_STATUS, ArchiveJob } from "../ArchiveJob";

describe("ArchiveJob", () => {
  it("falls back to pending when the response has no status", () => {
    const job = new ArchiveJob({});

    expect(job.status).toBe(ARCHIVE_STATUS.PENDING);
    expect(job.is_terminal).toBe(false);
    expect(job.has_failed).toBe(false);
  });

  it("accepts the legacy state key", () => {
    const job = new ArchiveJob({ state: ARCHIVE_STATUS.RUNNING });

    expect(job.status).toBe(ARCHIVE_STATUS.RUNNING);
  });

  it("computes progress from processed and total files", () => {
    const job = new ArchiveJob({ total_files: 4, processed_files: 1 });

    expect(job.progress_percent).toBe(25);
  });

  it("returns null progress for an empty manifest", () => {
    const job = new ArchiveJob({ total_files: 0, processed_files: 0 });

    expect(job.progress_percent).toBeNull();
  });

  it("caps progress at one hundred percent", () => {
    const job = new ArchiveJob({ total_files: 2, processed_files: 3 });

    expect(job.progress_percent).toBe(100);
  });

  it("requires a file URL to be ready", () => {
    const job = new ArchiveJob({
      status: ARCHIVE_STATUS.READY,
      file_url: "/download/jobs/1/file/",
    });

    expect(job.is_ready).toBe(true);
    expect(job.is_terminal).toBe(true);
  });

  it("treats a ready job without a file URL as not ready", () => {
    const job = new ArchiveJob({ status: ARCHIVE_STATUS.READY });

    expect(job.is_ready).toBe(false);
  });

  it.each([
    ARCHIVE_STATUS.FAILED,
    ARCHIVE_STATUS.CANCELLED,
    ARCHIVE_STATUS.EXPIRED,
  ])("marks %s as a terminal error", (status) => {
    const job = new ArchiveJob({ status });

    expect(job.has_failed).toBe(true);
    expect(job.is_terminal).toBe(true);
  });

  it("prefers the backend error message", () => {
    const job = new ArchiveJob({
      status: ARCHIVE_STATUS.FAILED,
      last_error: "Disk is full.",
    });

    expect(job.error_message).toBe("Disk is full.");
  });

  it("has a fallback message for each error status", () => {
    const job = new ArchiveJob({ status: ARCHIVE_STATUS.EXPIRED });

    expect(job.error_message).toContain("expired");
  });

  it("converts retry_after to milliseconds with a default fallback", () => {
    expect(new ArchiveJob({ retry_after: 5 }).retry_delay_ms).toBe(5000);
    expect(new ArchiveJob({ retry_after: 0 }).retry_delay_ms).toBe(2000);
  });
});
