// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

const rootResponse = {
  current: {name: "shared", type: "directory", path: "/"},
  ancestors: [],
  children: [{name: "child", type: "directory", path: "/child"}],
};

const childResponse = {
  current: {name: "child", type: "directory", path: "/child"},
  ancestors: [{name: "shared", type: "directory", path: "/"}],
  children: [],
};

const flushPromises = () => new Promise((resolve) => { setTimeout(resolve, 0); });

describe("public share routing", () => {
  let requestCount;

  beforeEach(() => {
    requestCount = 0;
    vi.spyOn(m, "request").mockImplementation((url) => {
      requestCount += 1;
      const urlString = typeof url === "string" ? url : url.url;
      return Promise.resolve(urlString.endsWith("/child") ? childResponse : rootResponse);
    });
    window.history.replaceState({}, "", "/s/token/");
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("loads each share path exactly once when navigating", async () => {
    await import("../index.js");

    await vi.waitFor(() => {
      expect(requestCount).toBe(1);
    });
    expect(m.route.get()).toBe("/s/token/");

    m.route.set("/s/token/child");
    expect(window.location.pathname).toBe("/s/token/child");
    await flushPromises();
    expect(m.route.get()).toBe("/s/token/child");

    await vi.waitFor(() => {
      expect(requestCount).toBe(2);
    });

    await flushPromises();
    expect(requestCount).toBe(2);
    expect(document.body.textContent).toContain("child");
  });
});
