import { describe, expect, it } from "vitest";

import { getFsNodeNameErrors } from "../validation";

describe("getFsNodeNameErrors()", () => {
  it("accepts a regular file name", () => {
    expect(getFsNodeNameErrors("report 2026.txt")).toEqual([]);
  });

  it("requires a name", () => {
    expect(getFsNodeNameErrors("")).toEqual(["Name is required"]);
  });

  it("rejects dot names", () => {
    expect(getFsNodeNameErrors(".")[0]).toContain('"." or ".."');
    expect(getFsNodeNameErrors("..")[0]).toContain('"." or ".."');
  });

  it("rejects names longer than 255 characters", () => {
    expect(getFsNodeNameErrors("a".repeat(256))[0]).toContain("255");
  });

  it("rejects reserved characters", () => {
    for (const name of ['a/b', "a\\b", "a:b", "a<b", "a>b", 'a"b', "a|b", "a?b", "a*b"]) {
      expect(getFsNodeNameErrors(name)[0]).toContain("reserved characters");
    }
  });
});
