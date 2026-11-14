import { describe, expect, it } from "vitest";

import FsNode from "../FsNode";

describe("FsNode model", () => {
  it("stores the UUID identity fields", () => {
    const node = new FsNode({
      id: "11111111-1111-1111-1111-111111111111",
      parent_id: "22222222-2222-2222-2222-222222222222",
      name: "report.pdf",
      type: "file",
    });

    expect(node.id).toBe("11111111-1111-1111-1111-111111111111");
    expect(node.parent_id).toBe("22222222-2222-2222-2222-222222222222");
    expect(node.name).toBe("report.pdf");
  });

  it("defaults id and parent_id to null", () => {
    const node = new FsNode({ name: "report.pdf", type: "file" });

    expect(node.id).toBeNull();
    expect(node.parent_id).toBeNull();
  });
});
