import m from "mithril";
import { DashboardSideBar } from "../sidebar";
import { ModalsAndBackdrop } from "../bootstrap/modal";
import { DashboardMobileNavBarView } from "./DashboardMobileNavBarView";

const getActiveId = () => {
  const { pathname } = window.location;
  if (pathname === "/shares") {
    return "shares";
  }
  return pathname.split("/")[1] || "files";
};

/**
 * Shared dashboard layout: sidebar, mobile navigation and modal host.
 */
export const DashboardShell = {
  view(vnode) {
    const sidebarUrls = JSON.parse(document.getElementById("dashboard-urls").textContent);
    const activeId = vnode.attrs.activeId || getActiveId();

    return [
      m(".d-flex w-100", [
        m(DashboardSideBar, { activeId, items: sidebarUrls }),
        m(".flex-grow-1 vh-100 overflow-y-auto bg-light",
          m(".container-fluid", [
            m(DashboardMobileNavBarView, { activeId, items: sidebarUrls }),
            vnode.children,
          ])
        ),
      ]),
      m(ModalsAndBackdrop),
    ];
  },
};
