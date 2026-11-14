import {FsNodeList} from "@polyfile/core/services/FsNodeList";

export class ShareFsNodeListService extends FsNodeList {
  constructor() {
    super();
    // The ancestor chain starts at the share root; its name stays hidden.
    this.stripShareRoot = true;
  }

  load(url, params) {
    return super.load(url, params).then(() => {
      if (!this.has_error && this.current?.type === "file") {
        // A shared file has no children, so expose the file itself as the only item.
        this.elements = [this.current];
      }
    });
  }
}

export const ShareFsNodeList = new ShareFsNodeListService();
