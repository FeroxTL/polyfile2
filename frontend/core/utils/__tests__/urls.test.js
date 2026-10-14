import { describe, it, expect } from "vitest";
import { encodePath, joinPath } from "../urls";

describe("joinPath() utility", () => {
  it("should join simple paths", () => {
    expect(joinPath("foo", "bar")).toBe("foo/bar");
  });

  it("should preserve leading slash for absolute paths", () => {
    expect(joinPath("/foo", "bar")).toBe("/foo/bar");
  });

  it("should handle root path (single slash)", () => {
    expect(joinPath("/", "foo")).toBe("/foo");
  });

  it("should handle multiple segments with root", () => {
    expect(joinPath("/", "foo", "bar")).toBe("/foo/bar");
  });

  it("should ignore empty strings and nulls", () => {
    const emptyObject = {};

    expect(joinPath("", "foo", emptyObject.missing, "bar")).toBe("foo/bar");
  });

  it("should remove extra slashes in the middle", () => {
    expect(joinPath("foo/", "/bar")).toBe("foo/bar");
    expect(joinPath("foo//", "///bar")).toBe("foo/bar");
  });

  it("should handle multiple segments", () => {
    expect(joinPath("a", "b", "c", "d")).toBe("a/b/c/d");
  });
});

describe("encodePath() utility", () => {
  it("should encode unsafe characters in every segment", () => {
    expect(encodePath("/docs/report #1.txt")).toBe("/docs/report%20%231.txt");
  });

  it("should encode percent signs and question marks", () => {
    expect(encodePath("/100%/what?.txt")).toBe("/100%25/what%3F.txt");
  });

  it("should preserve leading and separator slashes", () => {
    expect(encodePath("/a/b/c")).toBe("/a/b/c");
  });

  it("should handle empty and nullish values", () => {
    const emptyObject = {};

    expect(encodePath("")).toBe("");
    expect(encodePath(null)).toBe("");
    expect(encodePath(emptyObject.missing)).toBe("");
  });
});
