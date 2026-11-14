import m from "mithril";
import { Modal, closeModal } from "../bootstrap/modal";
import Button from "@polyfile/core/ui-kit/button";
import {Input} from "@polyfile/core/ui-kit/input";
import {ShareService} from "../services/ShareService";

const ERROR_CODE_ZERO = 0;
const COPY_FEEDBACK_TIMEOUT_MS = 2000;
const DATE_SLICE_LOCALTIME = 16;

const STATUS_ACTIVE = "active";
const STATUS_REVOKED = "revoked";
const STATUS_EXPIRED = "expired";

const STATUS_BADGES = {
  [STATUS_ACTIVE]: { label: "Active", className: "text-bg-success" },
  [STATUS_EXPIRED]: { label: "Expired", className: "text-bg-warning" },
  [STATUS_REVOKED]: { label: "Revoked", className: "text-bg-secondary" },
};

/**
 * Convert an ISO timestamp to the local value expected by datetime-local inputs.
 */
const toDateTimeLocalValue = (value) => {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, DATE_SLICE_LOCALTIME)
};

/**
 * Convert a datetime-local value to an ISO timestamp, or null to clear expiration.
 */
const toExpiresAt = (value) => (value ? new Date(value).toISOString() : null);

/**
 * Resolve the lifecycle status of a share.
 *
 * The owner's share list sends an explicit ``status``, while FsNode payloads
 * (file browser) only expose timestamps, so expiration is derived locally when
 * needed. Revocation wins over expiration, matching the backend behaviour.
 */
const resolveShareStatus = (share) => {
  if (!share) {
    return null;
  }

  const status = share.status || null;
  const revokedAt = share.revokedAt || share.revoked_at || null;
  const expiresAt = share.expiresAt || share.expires_at || null;

  if (revokedAt || status === STATUS_REVOKED) {
    return STATUS_REVOKED;
  }

  if (expiresAt) {
    const timestamp = new Date(expiresAt).getTime();
    if (!Number.isNaN(timestamp) && timestamp <= Date.now()) {
      return STATUS_EXPIRED;
    }
  }

  return status || STATUS_ACTIVE;
};

const isShareActive = (share) => resolveShareStatus(share) === STATUS_ACTIVE;

const formatDetail = (detail) => {
  if (Array.isArray(detail)) {
    return detail.join("; ");
  }
  if (detail && typeof detail === "object") {
    return Object.values(detail)
      .flatMap((value) => Array.isArray(value) ? value : [value])
      .join("; ");
  }
  return String(detail);
};

const getDetailFromError = (error) => {
  if (!error) {
    return "Something went wrong";
  }
  if (error.code === ERROR_CODE_ZERO || error.response === null || typeof error.response === "undefined") {
    return error.message || "Unknown error, please try again later";
  }
  if (typeof error.response === "object" && error.response.detail) {
    return formatDetail(error.response.detail);
  }
  if (typeof error.response === "object" && error.response.description) {
    return String(error.response.description);
  }
  if (typeof error.response === "string" && error.response) {
    return error.response;
  }
  return error.message || "Something went wrong";
};

function SharedNode(data) {
  this.id = data.id;
  this.url = data.url;
  this.status = data.status;
  this.expiresAt = data.expires_at;
  this.revokedAt = data.revoked_at;
}

const ShareDirectoryModal = {
  oninit(vnode) {
    const { share } = vnode.attrs;
    vnode.state.share = share && new SharedNode(share);
    vnode.state.formExpiresAt = toDateTimeLocalValue(vnode.state.share?.expiresAt);
    vnode.state.loading = false;
    vnode.state.error = null;
    vnode.state.copied = false;
    vnode.state.copyError = null;
    vnode.state.revoked = false;
  },

  submit(vnode) {
    if (vnode.state.loading) {
      return;
    }

    vnode.state.loading = true;
    vnode.state.error = null;
    vnode.state.revoked = false;

    const { nodeId, onUpdate } = vnode.attrs;
    const expiresAt = toExpiresAt(vnode.state.formExpiresAt);

    ShareService.create(nodeId, expiresAt)
      .then((data) => {
        vnode.state.share = data && new SharedNode(data);
        vnode.state.shareLink = vnode.state.share?.url || "";

        if (typeof onUpdate === "function") {
          onUpdate(data);
        }
        return data;
      })
      .catch((error) => {
        vnode.state.error = getDetailFromError(error);
      })
      .finally(() => {
        vnode.state.loading = false;
      });
  },

  revoke(vnode) {
    const { onUpdate } = vnode.attrs;
    const { share } = vnode.state;

    if (vnode.state.loading || !share) {
      return;
    }

    vnode.state.loading = true;
    vnode.state.error = null;

    ShareService.revoke(share)
      .then(() => {
        vnode.state.share = null;
        vnode.state.shareLink = "";
        vnode.state.copied = false;
        vnode.state.copyError = null;
        vnode.state.revoked = true;
        vnode.state.formExpiresAt = "";

        if (typeof onUpdate === "function") {
          onUpdate(null);
        }
      })
      .catch((error) => {
        vnode.state.error = getDetailFromError(error);
      })
      .finally(() => {
        vnode.state.loading = false;
      });
  },

  copyToClipboard(state) {
    if (!state.share.url) {
      return;
    }

    if (!navigator.clipboard) {
      state.copyError = "Clipboard is not available. Please copy the link manually.";
      m.redraw();
      return;
    }

    navigator.clipboard.writeText(state.share.url)
      .then(() => {
        state.copied = true;
        state.copyError = null;
        m.redraw();
        setTimeout(() => {
          state.copied = false;
          m.redraw();
        }, COPY_FEEDBACK_TIMEOUT_MS);
      })
      .catch(() => {
        state.copyError = "Could not copy the link. Please copy it manually.";
        m.redraw();
      });
  },

  renderExpiration(vnode) {
    return m(".mb-3", [
      m("label.form-label", "Expiration (optional)"),
      m(Input, {
        type: "datetime-local",
        value: toDateTimeLocalValue(vnode.state.formExpiresAt),
        oninput: (event) => {
          vnode.state.formExpiresAt = event.target.value;
        },
      }),
      m(".form-text", "Leave empty for a link that does not expire."),
    ]);
  },

  renderCreateAction(vnode) {
    const isDirectory = vnode.attrs.type === "directory";
    return m(".mb-3", [
      m("p", isDirectory
        ? "Click the button below to create a public sharing link for this directory."
        : "Click the button below to create a public sharing link for this file."),
      this.renderExpiration(vnode),
      m(Button, {
        type: "submit",
        disabled: vnode.state.loading,
      }, "Create Share Link"),
    ]);
  },

  renderStatusNotice(vnode) {
    const status = resolveShareStatus(vnode.state.share);

    if (status === STATUS_EXPIRED) {
      return m(".alert.alert-warning", [
        m("p.mb-1", "This public link has expired and can no longer be opened."),
        m("p.mb-0", "Set a new expiration in the future and click \"Reactivate share\" to make it available again."),
      ]);
    }

    if (status === STATUS_REVOKED) {
      return m(".alert.alert-secondary", [
        m("p.mb-1", "This public link has been revoked and can no longer be opened."),
        m("p.mb-0", "Set an expiration below (or leave it empty) and click \"Reactivate share\" to create a new link."),
      ]);
    }

    return null;
  },

  renderShareStatus(share) {
    const status = resolveShareStatus(share);
    const badge = STATUS_BADGES[status];

    if (!badge) {
      return null;
    }

    return m("div.d-flex.align-items-center.mb-2", [
      m("span.badge", { class: badge.className }, badge.label),
    ]);
  },

  renderShareLink(vnode) {
    const { state } = vnode;
    const active = isShareActive(state.share);
    const hasUrl = Boolean(state.share?.url);

    return m(".mb-3", [
      this.renderShareStatus(state.share),
      m(".input-group", [
        m(Input, {
          type: "text",
          readOnly: true,
          value: state.share?.url || "",
          disabled: Boolean(!hasUrl),
          className: "font-monospace",
          placeholder: active ? "Public link will appear here" : "This link is no longer usable",
        }),
        m(Button, {
          type: "button",
          class: state.copied ? "btn-success" : "btn-primary",
          disabled: Boolean(!hasUrl) || !active,
          onclick: () => this.copyToClipboard(state),
        }, state.copied ? "Copied!" : "Copy"),
      ]),
      m(".mt-3", [
        this.renderExpiration(vnode),
        m(Button, {
          type: "submit",
          class: "btn-outline-primary",
          disabled: state.loading,
        }, active ? "Update expiration" : "Reactivate share"),
      ]),
    ]);
  },

  renderBody(vnode) {
    const { state } = vnode;
    return m(".modal-body", [
      state.error && m(".alert alert-danger", state.error),
      state.copyError && m(".alert alert-warning", state.copyError),
      state.revoked && m(".alert alert-success", "The share link has been revoked."),
      state.share && this.renderStatusNotice(vnode),
      !state.share && !state.loading && this.renderCreateAction(vnode),
      state.share && this.renderShareLink(vnode),
      state.loading && m(".spinner-border text-primary", {}),
    ]);
  },

  view(vnode) {
    const { type, modalId } = vnode.attrs;
    const { state } = vnode;
    const title = type === "directory" ? "Share Directory" : "Share File";

    return (
      m(Modal, vnode.attrs,
        m(".modal-dialog",
          m(".modal-content", [
            m(Modal.modalHeader, { ...vnode.attrs, title }),
            m("form.has-validation", {
              onsubmit: (e) => {
                e.preventDefault();
                this.submit(vnode);
              },
            }, [
              this.renderBody(vnode),
              m(".modal-footer", [
                state.share?.url && isShareActive(state.share) && m(Button, {
                  type: "button",
                  class: "btn-warning me-auto",
                  disabled: state.loading,
                  onclick: () => this.revoke(vnode),
                }, "Revoke"),
                m(Button, {
                  type: "button",
                  class: "btn-secondary",
                  onclick: () => closeModal(modalId),
                }, "Close"),
              ]),
            ]),
          ])
        ),
      )
    );
  }
};

export { ShareDirectoryModal, isShareActive, resolveShareStatus };
