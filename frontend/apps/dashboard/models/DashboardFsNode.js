import FsNode from "@polyfile/core/models/FsNode";

export class DashboardFsNode extends FsNode {
  constructor(data) {
    super(data);
    this.upload_status = data.upload_status || "done";
  }
}
