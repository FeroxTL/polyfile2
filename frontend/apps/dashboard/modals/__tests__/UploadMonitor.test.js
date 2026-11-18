// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

import { UploadManager } from "../../services/UploadManager";
import {
  UploadMonitorDocked,
  UploadMonitorModal,
} from "../UploadMonitor";

const makeJob = (overrides = {}) => ({
  id: "upload-1",
  file: { name: "report.pdf" },
  name: "report.pdf",
  size: 1024 * 1024,
  parentId: null,
  loaded: 0,
  status: "uploading",
  error: null,
  node: null,
  uploadUrl: "/upload/token",
  xhr: null,
  replace: false,
  createdNode: false,
  ...overrides,
});

let root = null;

const render = (component, attrs = {}) => {
  root = document.createElement("div");
  document.body.appendChild(root);
  m.render(root, m(component, attrs));
  return root;
};

describe("upload monitor", () => {
  beforeEach(() => {
    UploadManager.reset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    UploadManager.reset();
    root?.remove();
  });

  it("stays hidden on desktop until uploads start", () => {
    const element = render(UploadMonitorDocked);

    expect(element.querySelector(".upload-monitor")).toBeNull();
  });

  it("renders the status, overall percent and file list", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob({ loaded: 512 * 1024 })];

    const element = render(UploadMonitorDocked);

    expect(element.querySelector(".upload-monitor__header").textContent)
      .toContain("Uploading");
    expect(element.querySelector(".upload-monitor__header").textContent)
      .toContain("50%");
    expect(element.textContent).toContain("report.pdf");
    expect(element.textContent).toContain("1.0 MB");
    expect(element.textContent).toContain("50%");
  });

  it("shows overall progress and completed file count in the header", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [
      makeJob({ id: "upload-1", status: "done", size: 100, loaded: 100 }),
      makeJob({
        id: "upload-2",
        name: "photo.jpg",
        status: "uploading",
        size: 300,
        loaded: 150,
      }),
    ];

    const element = render(UploadMonitorDocked);
    const header = element.querySelector(".upload-monitor__header").textContent;

    expect(header).toContain("63%");
    expect(header).toContain("1/2 files");
  });

  it("collapses the body when the header is clicked", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob()];

    const element = render(UploadMonitorDocked);
    element.querySelector(".upload-monitor__header").click();

    expect(UploadManager.collapsed).toBe(true);
  });

  it("shows the first error with a red reason and action buttons", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [
      makeJob({
        status: "conflict",
        error: {
          code: 409,
          errorId: "FsNodeExistsError",
          existingType: "file",
          retryable: false,
        },
      }),
    ];

    const element = render(UploadMonitorDocked);
    const status = element.querySelector(".upload-monitor__job-status");

    expect(status.textContent).toContain("file already exists");
    expect(status.className).toContain("text-danger");
    expect(element.textContent).toContain("already exists in this folder");
    expect(element.textContent).toContain("Replace");
    expect(element.textContent).toContain("Don't upload");
  });

  it("shows only the first unresolved error", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [
      makeJob({
        id: "upload-1",
        name: "first.txt",
        status: "conflict",
        error: { code: 409, errorId: "FsNodeExistsError", existingType: "file" },
      }),
      makeJob({
        id: "upload-2",
        name: "second.txt",
        status: "error",
        error: { code: 0, retryable: true },
      }),
    ];

    const element = render(UploadMonitorDocked);
    const alerts = element.querySelectorAll(".alert.alert-danger");

    expect(alerts).toHaveLength(1);
    expect(alerts[0].textContent).toContain("first.txt");
    expect(alerts[0].textContent).not.toContain("second.txt");
  });

  it("closes the panel when all uploads are finished", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob({ status: "done", loaded: 1024 * 1024 })];

    const element = render(UploadMonitorDocked);
    const closeButton = element.querySelector(".upload-monitor__close");

    closeButton.click();

    expect(UploadManager.visible).toBe(false);
  });

  it("collapses without closing while uploads are running", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob()];

    const element = render(UploadMonitorDocked);
    element.querySelector(".upload-monitor__collapse").click();

    expect(UploadManager.collapsed).toBe(true);
    expect(UploadManager.visible).toBe(true);
  });

  it("does not mix collapsing and closing on a finished panel", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob({ status: "done", loaded: 1024 * 1024 })];

    const element = render(UploadMonitorDocked);
    element.querySelector(".upload-monitor__collapse").click();

    expect(UploadManager.collapsed).toBe(true);
    expect(UploadManager.visible).toBe(true);

    m.render(root, m(UploadMonitorDocked));
    element.querySelector(".upload-monitor__close").click();

    expect(UploadManager.visible).toBe(false);
  });

  it("shows no close button while uploads are running", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob()];

    const element = render(UploadMonitorDocked);

    expect(element.querySelector(".upload-monitor__close")).toBeNull();
  });

  it("hides upload actions when there is nothing to cancel", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob({ status: "done", loaded: 1024 * 1024 })];

    const element = render(UploadMonitorDocked);

    expect(element.querySelector(".upload-monitor__actions-toggle")).toBeNull();
  });

  it("opens the actions menu and cancels all uploads", () => {
    const cancelAll = vi.spyOn(UploadManager, "cancelAll")
      .mockImplementation(() => null);
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob({ status: "uploading" })];

    const element = render(UploadMonitorDocked);
    element.querySelector(".upload-monitor__actions-toggle").click();
    m.render(root, m(UploadMonitorDocked));

    const menu = element.querySelector(".upload-monitor__menu");
    expect(menu).not.toBeNull();
    expect(menu.textContent).toContain("Cancel all uploads");

    menu.querySelector(".dropdown-item").click();

    expect(cancelAll).toHaveBeenCalled();
  });

  it("closes the actions menu when clicking outside", () => {
    UploadManager.visible = true;
    UploadManager.jobs = [makeJob({ status: "uploading" })];

    const element = render(UploadMonitorDocked);
    element.querySelector(".upload-monitor__actions-toggle").click();
    m.render(root, m(UploadMonitorDocked));

    element.querySelector(".upload-monitor__menu-backdrop").click();
    m.render(root, m(UploadMonitorDocked));

    expect(element.querySelector(".upload-monitor__menu")).toBeNull();
  });

  it("calls replace from the conflict action", () => {
    const replace = vi.spyOn(UploadManager, "replace").mockImplementation(() => null);
    UploadManager.visible = true;
    UploadManager.jobs = [
      makeJob({
        status: "conflict",
        error: {
          code: 409,
          errorId: "FsNodeExistsError",
          existingType: "file",
          retryable: false,
        },
      }),
    ];

    const element = render(UploadMonitorDocked);
    const replaceButton = Array.from(element.querySelectorAll(".alert button"))
      .find((button) => button.textContent === "Replace");

    replaceButton.click();

    expect(replace).toHaveBeenCalledWith(UploadManager.jobs[0]);
  });

  it("renders the mobile variant as a standard modal", () => {
    UploadManager.jobs = [makeJob()];

    const element = render(UploadMonitorModal, {
      modalId: ["modal"],
      modalShow: true,
    });

    expect(element.querySelector(".modal")).not.toBeNull();
    expect(element.querySelector(".modal-content")).not.toBeNull();
    expect(element.querySelector(".upload-monitor__header--modal")).not.toBeNull();
    expect(element.textContent).toContain("report.pdf");
  });
});
