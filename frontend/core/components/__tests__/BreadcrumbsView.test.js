import { describe, expect, it, vi } from "vitest";

import { BreadcrumbsView } from "../BreadcrumbsView";

const collectBreadcrumbNames = (node, names = []) => {
  if (node === null || typeof node === "undefined") {
    return names;
  }
  if (Array.isArray(node)) {
    node.forEach((child) => collectBreadcrumbNames(child, names));
    return names;
  }
  if (typeof node !== "object") {
    return names;
  }
  if (node.attrs && typeof node.attrs.name === "string") {
    names.push(node.attrs.name);
  }
  collectBreadcrumbNames(node.children, names);
  return names;
};

const collectBreadcrumbVnodes = (node, crumbs = []) => {
  if (node === null || typeof node === "undefined") {
    return crumbs;
  }
  if (Array.isArray(node)) {
    node.forEach((child) => collectBreadcrumbVnodes(child, crumbs));
    return crumbs;
  }
  if (typeof node !== "object") {
    return crumbs;
  }
  if (node.attrs && typeof node.attrs.index === "number") {
    crumbs.push(node);
  }
  collectBreadcrumbVnodes(node.children, crumbs);
  return crumbs;
};

const requireBreadcrumbs = (pathSegments, attrs = {}) => {
  const breadcrumbNodes = pathSegments.map((name, index) => ({
    name,
    id: `node-${index}`,
  }));
  const fsnodeList = {
    current: { name: pathSegments[pathSegments.length - 1] || "" },
    pathSegments,
    breadcrumbNodes,
  };
  const vnode = {
    attrs: {
      FsNodeList: fsnodeList,
      getPublicUrl: (path) => `/files${path}`,
      ...attrs,
    },
  };

  return {
    breadcrumbNodes,
    rendered: new BreadcrumbsView(vnode).view(vnode),
  };
};

describe("BreadcrumbsView", () => {
  it("renders the ancestor chain followed by the current node name", () => {
    const { rendered } = requireBreadcrumbs(["root", "sub"]);

    expect(collectBreadcrumbNames(rendered)).toEqual(["Files", "root", "sub"]);
  });

  it("renders only the root crumb at the top level", () => {
    const { rendered } = requireBreadcrumbs([]);

    expect(collectBreadcrumbNames(rendered)).toEqual(["Files"]);
  });

  it("passes the crumb node and path to the navigation handler", () => {
    const onNavigate = vi.fn();
    const { breadcrumbNodes, rendered } = requireBreadcrumbs(
      ["root", "sub"],
      { onNavigate },
    );
    const parentCrumb = collectBreadcrumbVnodes(rendered)
      .find((crumb) => crumb.attrs.name === "root");

    expect(parentCrumb.attrs.node).toBe(breadcrumbNodes[0]);

    parentCrumb.attrs.onNavigate(parentCrumb.attrs.node, "root");
    expect(onNavigate).toHaveBeenCalledWith(breadcrumbNodes[0], "root");
  });
});
