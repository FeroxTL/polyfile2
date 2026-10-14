import m from "mithril";
import {ModalsAndBackdrop} from "../dashboard/bootstrap/modal";
import {FsNodeListView} from "@polyfile/core/components/FsNodeListView";
import {ShareFsNodeList} from "./services/shareFsNodeList";
import {SHARE_API_DETAIL_URL, SHARE_URL} from "./constants/endpoints";
import {BreadcrumbsView} from "@polyfile/core/components/BreadcrumbsView";
import {joinPath} from "@polyfile/core/utils/urls";
import {ShareFsNodeActionbarView} from "./components/ShareFsNodeActionbarView";


const ShareDetailView = {
  oninit(vnode) {
    this.loadData(vnode.attrs)
  },

  loadData(attrs) {
    return ShareFsNodeList.load(m.buildPathname(SHARE_API_DETAIL_URL, {
      share_token: attrs.share_token,
      key: attrs.key,
    }))
  },

  view(vnode) {
    const selectedList = ShareFsNodeList.elements.filter((item) => item.selected);
    const navigationHandler = (path, name) => {
      m.route.set(
        SHARE_URL, {
          share_token: m.route.param("share_token"),
          key: joinPath(path, name).replace(/^\/+/u, ""),
        },
      );
    };

    return m("div.flex-grow-1 vh-100 overflow-y-auto bg-light", [
      m(".container-fluid mt-3", [
        m("h1.h2 border-bottom", ShareFsNodeList.current?.name),
        selectedList.length > 0
          ? m(".card text-bg-dark sticky-top", m(".card-body p-2 ps-3", m(ShareFsNodeActionbarView, {
            selectedList,
            onClose: () => ShareFsNodeList.selectFsNode(),
          })))
          : m(BreadcrumbsView, {
            FsNodeList: ShareFsNodeList,
            getPublicUrl: (path) => m.buildPathname(SHARE_URL, {
              share_token: m.route.param("share_token"),
              key: path.replace(/^\/+/u, ""),
            }),
          }),
        m(FsNodeListView, {
          fsnodeList: ShareFsNodeList,
          onRetry: () => {this.loadData(vnode.attrs)},
          navigationHandler
        }),
      ]),

      // Modals
      m(ModalsAndBackdrop),
    ]);
  }
}

export default ShareDetailView;
