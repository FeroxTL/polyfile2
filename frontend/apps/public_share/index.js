import ShareDetailComponent from "./ShareDetailView";
import m from "mithril";

// This behavior is supported by backend
m.route.prefix = "";

m.route(document.body, "/error", {
  "/error": {
    // TODO
    view() {
      return m("div", "That's an error")
    }
  },
  "/s/:share_token/:key...": ShareDetailComponent,
})
