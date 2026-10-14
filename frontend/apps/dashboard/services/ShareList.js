import m from "mithril";

import { API_V1_SHARE_LIST, API_V1_SHARE_PERMANENT_DELETE } from "../constants/endpoints";
import { ShareService } from "./ShareService";

const DEFAULT_STATUS = "all";
const DEFAULT_PAGE_SIZE = 25;

export class ShareListService {
  constructor() {
    this.items = [];
    this.total = 0;
    this.page = 1;
    this.pageSize = DEFAULT_PAGE_SIZE;
    this.status = DEFAULT_STATUS;
    this.isLoading = false;
    this.error = null;
  }

  load(options = {}) {
    const status = options.status || this.status || DEFAULT_STATUS;
    const page = options.page || this.page || 1;
    const pageSize = options.pageSize || this.pageSize || DEFAULT_PAGE_SIZE;

    this.status = status;
    this.page = page;
    this.pageSize = pageSize;
    this.isLoading = true;
    this.error = null;

    const query = {
      status,
      page,
      page_size: pageSize,
    };

    return m.request(API_V1_SHARE_LIST, {
      method: "GET",
      params: query,
    })
      .then((data) => {
        this.items = Array.isArray(data.items) ? data.items : [];
        this.total = data.total || 0;
        this.page = data.page || page;
        this.pageSize = data.page_size || pageSize;
        this.error = null;
        return data;
      })
      .catch((error) => {
        this.error = error;
        throw error;
      })
      .finally(() => {
        this.isLoading = false;
      });
  }

  // eslint-disable-next-line class-methods-use-this
  revoke(share) {
    return ShareService.revoke(share);
  }

  // eslint-disable-next-line class-methods-use-this
  deletePermanent(share) {
    const shareToken = share?.id;
    if (!shareToken) {
      return Promise.resolve();
    }

    return m.request(m.buildPathname(API_V1_SHARE_PERMANENT_DELETE, {
      share_token: shareToken,
    }), {
      method: "DELETE",
    });
  }
}

export const ShareList = new ShareListService();
