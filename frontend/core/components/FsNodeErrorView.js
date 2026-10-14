import m from "mithril";
import Card from "@polyfile/core/ui-kit/card";


export class FsNodeErrorView {
  constructor(vnode) {
    this.error = vnode.attrs.error;
    this.allowGotoMain = vnode.attrs.allowGotoMain === true;
  }

  get title() {
    const {error} = this;
    if (error.response?.description) {
      return error.response.description
    }

    return ""
  }

  get message() {
    const {error} = this;
    if (error.response?.detail) {
      return error.response.detail;
    }
    return "Unknown error, please try again later"
  }

  view(vnode) {
    const { onRetry } = vnode.attrs;

    if (!this.error) {
      return null;
    }

    return m(Card, {
      class: "w-50 align-self-center mt-5 bg-warning",
      title: this.title
    }, [
      m("p.card-text", this.message),
      m("button.btn btn-primary", { onclick: onRetry || (() => { window.location.reload() }) }, "Retry"),
      this.allowGotoMain && m("a", { href: "/", class: "btn btn-primary me-2" }, "Main page"),
    ]);
  }
}
