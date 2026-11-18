import { describe, expect, it } from "vitest";

import { getApiErrorDetail } from "../errors";

describe("getApiErrorDetail()", () => {
  it("returns a string detail", () => {
    const error = { code: 409, response: { detail: "Already exists" } };

    expect(getApiErrorDetail(error)).toBe("Already exists");
  });

  it("joins array details", () => {
    const error = { code: 400, response: { detail: ["First", "Second"] } };

    expect(getApiErrorDetail(error)).toBe("First; Second");
  });

  it("flattens Marshmallow object details", () => {
    const error = {
      code: 400,
      response: { detail: { name: ["Required"], parent_id: ["Invalid"] } },
    };

    expect(getApiErrorDetail(error)).toBe("Required; Invalid");
  });

  it("falls back for network errors and missing details", () => {
    expect(getApiErrorDetail(null)).toBe("Unknown error, please try again later");
    expect(getApiErrorDetail({ code: 0, response: null }))
      .toBe("Unknown error, please try again later");
    expect(getApiErrorDetail({ code: 500, response: {} }))
      .toBe("Unknown error, please try again later");
  });
});
