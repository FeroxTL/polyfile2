/*
 * FsNode model.
 */
export default class FsNode {
  constructor(data) {
    this.name = data.name || "";
    this.type = data.type || "";
    this.created_at = data.created_at || null;
    this.modified_at = data.modified_at || null;
    this.size = data.size || 0;
    this.mime_type = data.mime_type || "";
    this.md5 = data.md5 || "";
    this.file = data.file || "";
    this.path = data.path || "";
    this.download_url = data.download_url || "";
    this.share = data.share || null;
    this.selected = false;
  }

  get is_shared() {
    return this.share !== null;
  }
}
