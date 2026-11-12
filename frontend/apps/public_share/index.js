import m from "mithril";
import {SHARE_URL} from "./constants/endpoints";
import {loadData, ShareDetailView} from "./ShareDetailView";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, "/error", {
  "/error": {
    // TODO
    view() {
      return m("div", "That's an error")
    }
  },
  [SHARE_URL]: {
    onmatch: (args) => {
      loadData(args);
      return ShareDetailView;
    }
  },
})
