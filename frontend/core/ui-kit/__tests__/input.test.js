import { describe, expect, it, vi } from "vitest";
import { Input } from "../input";

const renderInput = (attrs) => Input.view({ attrs });

describe("Input", () => {
  it("renders a plain value", () => {
    const [input] = renderInput({
      value: "https://example.com/s/token/",
      readOnly: true,
      placeholder: "Public link",
      className: "font-monospace",
      type: "text",
    });

    expect(input.tag).toBe("input");
    expect(input.attrs.value).toBe("https://example.com/s/token/");
    expect(input.attrs.readOnly).toBe(true);
    expect(input.attrs.placeholder).toBe("Public link");
    expect(input.attrs.className).toBe("form-control font-monospace");
    expect(input.attrs.type).toBe("text");
  });

  it("reads and updates a stream", () => {
    let current = "initial";
    const stream = vi.fn((next) => {
      if (typeof next !== "undefined") {
        current = next;
      }
      return current;
    });
    const oninput = vi.fn();
    const [input] = renderInput({ stream, oninput });

    expect(input.attrs.value).toBe("initial");

    input.attrs.oninput({ target: { value: "changed" } });

    expect(stream).toHaveBeenCalledWith("changed");
    expect(current).toBe("changed");
    expect(oninput).toHaveBeenCalledOnce();
  });

  it("does not mutate a plain value but forwards oninput", () => {
    const oninput = vi.fn();
    const [input] = renderInput({ value: "static", oninput });

    input.attrs.oninput({ target: { value: "typed" } });

    expect(input.attrs.value).toBe("static");
    expect(oninput).toHaveBeenCalledOnce();
  });

  it("marks the input invalid and renders feedback messages", () => {
    const [input, feedback] = renderInput({ value: "", errors: ["Required"] });

    expect(input.attrs.className).toContain("is-invalid");
    expect(feedback).toHaveLength(1);
    expect(feedback[0].children[0].children).toBe("Required");
  });

  it("combines class and className", () => {
    const [input] = renderInput({ value: "", class: "mb-2", className: "font-monospace" });

    expect(input.attrs.className).toBe("form-control mb-2 font-monospace");
  });

  it("requires a stream or a value", () => {
    expect(() => renderInput({})).toThrow("Argument 'stream' or 'value' is required");
  });
});
