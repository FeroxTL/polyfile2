// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import m from "mithril";

const rootResponse = {
  current: {id: "22222222-2222-2222-2222-222222222222", parent_id: null, name: "shared", type: "directory"},
  ancestors: [],
  children: [{id: "33333333-3333-3333-3333-333333333333", parent_id: "22222222-2222-2222-2222-222222222222", name: "child", type: "directory"}],
};

const childResponse = {
  current: {id: "33333333-3333-3333-3333-333333333333", parent_id: "22222222-2222-2222-2222-222222222222", name: "child", type: "directory"},
  ancestors: [{id: "22222222-2222-2222-2222-222222222222", name: "shared"}],
  children: [],
};

const flushPromises = () => new Promise((resolve) => { setTimeout(resolve, 0); });

describe("public share routing", () => {
  let requestCount = 0;

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
