import m from "mithril";
import { Modal, closeModal } from "../bootstrap/modal";
import Button from "@polyfile/core/ui-kit/button";
import { Input } from "@polyfile/core/ui-kit/input";
import { ShareService } from "../services/ShareService";
import {
  EXPIRATION_PRESETS,
  PRESET_CUSTOM,
  PRESET_NEVER,
  getExpirationSummary,
  getPresetDate,
  toDateTimeLocalValue,
  toExpiresAt,
  validateExpiration,
} from "./share_expiration";

const ERROR_CODE_ZERO = 0;
const COPY_FEEDBACK_TIMEOUT_MS = 2000;
const SAVED_FEEDBACK_TIMEOUT_MS = 2000;
const AUTO_SAVE_DEBOUNCE_MS = 500;

const STATUS_ACTIVE = "active";
const STATUS_REVOKED = "revoked";
const STATUS_EXPIRED = "expired";

const PRESET_CHOOSE = "";

// Mithril cannot schedule a redraw outside a mounted component (e.g. in tests).
const scheduleRedraw = () => {
  if (typeof window !== "undefined") {
    m.redraw();
  }
};

const STATUS_BADGES = {
  [STATUS_ACTIVE]: { label: "Active", className: "text-bg-success" },
  [STATUS_EXPIRED]: { label: "Expired", className: "text-bg-warning" },
  [STATUS_REVOKED]: { label: "Revoked", className: "text-bg-secondary" },
};

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
const isShareRevoked = (share) => resolveShareStatus(share) === STATUS_REVOKED;

const getInitialPreset = (share) => {
  if (isShareRevoked(share)) {
    return PRESET_CHOOSE;
  }
  return share?.expiresAt ? PRESET_CUSTOM : PRESET_NEVER;
};

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
    const { state } = vnode;

    state.share = share && new SharedNode(share);
    state.shareLink = state.share?.url || "";
    // Revoked shares need an explicit expiration choice to be reactivated.
    state.preset = getInitialPreset(state.share);
    state.formExpiresAt = toDateTimeLocalValue(state.share?.expiresAt);
    state.savedFormExpiresAt = state.formExpiresAt;
    state.savedPreset = state.preset;
    state.loading = false;
    state.saving = false;
    state.saveQueued = false;
    state.saveStatus = null;
    state.saveTimer = null;
    state.savedTimer = null;
    state.expirationError = null;
    state.error = null;
    state.copied = false;
    state.copyError = null;
    state.revoked = false;
  },

  onremove(vnode) {
    // Flush a pending debounced edit so closing the modal does not lose it.
    if (vnode.state.saveTimer) {
      ShareDirectoryModal.commitCustomExpiration(vnode);
    }
    clearTimeout(vnode.state.saveTimer);
    clearTimeout(vnode.state.savedTimer);
  },

  submit(vnode) {
    const { state } = vnode;
    if (state.loading) {
      return;
    }

    if (state.preset === PRESET_CUSTOM) {
      state.expirationError = validateExpiration(state.formExpiresAt);
      if (state.expirationError) {
        return;
      }
    }

    state.loading = true;
    state.error = null;
    state.revoked = false;

    const { nodeId, onUpdate } = vnode.attrs;
    const expiresAt = toExpiresAt(state.formExpiresAt);

    ShareService.create(nodeId, expiresAt)
      .then((data) => {
        state.share = data && new SharedNode(data);
        state.shareLink = state.share?.url || "";
        state.savedFormExpiresAt = state.formExpiresAt;
        state.savedPreset = state.preset;

        if (typeof onUpdate === "function") {
          onUpdate(data);
        }
        return data;
      })
      .catch((error) => {
        state.error = getDetailFromError(error);
      })
      .finally(() => {
        state.loading = false;
      });
  },

  setPreset(vnode, value) {
    const { state } = vnode;
    const preset = EXPIRATION_PRESETS.find((option) => option.value === value);

    if (!preset) {
      return;
    }

    clearTimeout(state.saveTimer);
    state.saveTimer = null;
    state.preset = value;
    state.expirationError = null;

    if (value === PRESET_CUSTOM) {
      // Reveal the exact date. A revoked share reactivates with a valid date.
      if (isShareRevoked(state.share) && !validateExpiration(state.formExpiresAt)) {
        ShareDirectoryModal.saveExpiration(vnode);
      }
      return;
    }

    state.formExpiresAt = value === PRESET_NEVER
      ? ""
      : toDateTimeLocalValue(getPresetDate(preset).toISOString());

    ShareDirectoryModal.saveExpiration(vnode);
  },

  setCustomExpiration(vnode, value) {
    const { state } = vnode;

    state.formExpiresAt = value;
    state.expirationError = null;
    clearTimeout(state.saveTimer);
    state.saveTimer = setTimeout(() => {
      ShareDirectoryModal.commitCustomExpiration(vnode);
      scheduleRedraw();
    }, AUTO_SAVE_DEBOUNCE_MS);
  },

  commitCustomExpiration(vnode) {
    const { state } = vnode;

    clearTimeout(state.saveTimer);
    state.saveTimer = null;

    if (state.preset !== PRESET_CUSTOM) {
      ShareDirectoryModal.saveExpiration(vnode);
      return;
    }

    state.expirationError = validateExpiration(state.formExpiresAt);
    if (!state.expirationError) {
      ShareDirectoryModal.saveExpiration(vnode);
    }
  },

  saveExpiration(vnode) {
    const { state } = vnode;

    if (!state.share) {
      return;
    }

    if (state.saving) {
      state.saveQueued = true;
      return;
    }

    const { formExpiresAt, preset } = state;

    if (formExpiresAt === state.savedFormExpiresAt && preset === state.savedPreset) {
      return;
    }

    state.saving = true;
    state.saveQueued = false;
    state.saveStatus = "saving";
    state.error = null;
    state.expirationError = null;
    scheduleRedraw();

    const expiresAt = toExpiresAt(formExpiresAt);
    const { nodeId, onUpdate } = vnode.attrs;

    ShareService.create(nodeId, expiresAt)
      .then((data) => {
        state.share = data ? new SharedNode(data) : state.share;
        state.shareLink = state.share?.url || "";
        state.savedFormExpiresAt = formExpiresAt;
        state.savedPreset = preset;
        state.saveStatus = "saved";

        clearTimeout(state.savedTimer);
        state.savedTimer = setTimeout(() => {
          state.saveStatus = null;
          scheduleRedraw();
        }, SAVED_FEEDBACK_TIMEOUT_MS);

        if (typeof onUpdate === "function") {
          onUpdate(data);
        }
      })
      .catch((error) => {
        state.error = getDetailFromError(error);
        state.saveStatus = null;

        // Keep a newer edit if the user changed the value while saving.
        if (state.formExpiresAt === formExpiresAt) {
          state.preset = state.savedPreset;
          state.formExpiresAt = state.savedFormExpiresAt;
        }
      })
      .finally(() => {
        state.saving = false;

        if (state.saveQueued) {
          state.saveQueued = false;
          ShareDirectoryModal.saveExpiration(vnode);
        }
        scheduleRedraw();
      });
  },

  revoke(vnode) {
    const { onUpdate } = vnode.attrs;
    const { state } = vnode;

    if (state.loading || state.saving || !state.share) {
      return;
    }

    state.loading = true;
    state.error = null;

    ShareService.revoke(state.share)
      .then(() => {
        state.share = null;
        state.shareLink = "";
        state.copied = false;
        state.copyError = null;
        state.revoked = true;
        state.preset = PRESET_NEVER;
        state.formExpiresAt = "";
        state.savedFormExpiresAt = "";
        state.savedPreset = PRESET_NEVER;
        state.saveStatus = null;
        state.expirationError = null;
        clearTimeout(state.saveTimer);

        if (typeof onUpdate === "function") {
          onUpdate(null);
        }
      })
      .catch((error) => {
        state.error = getDetailFromError(error);
      })
      .finally(() => {
        state.loading = false;
      });
  },

  copyToClipboard(state) {
    if (!state.share.url) {
      return;
    }

    if (!navigator.clipboard) {
      state.copyError = "Clipboard is not available. Please copy the link manually.";
      scheduleRedraw();
      return;
    }

    navigator.clipboard.writeText(state.share.url)
      .then(() => {
        state.copied = true;
        state.copyError = null;
        scheduleRedraw();
        setTimeout(() => {
          state.copied = false;
          scheduleRedraw();
        }, COPY_FEEDBACK_TIMEOUT_MS);
      })
      .catch(() => {
        state.copyError = "Could not copy the link. Please copy it manually.";
        scheduleRedraw();
      });
  },

  renderSaveStatus(vnode) {
    const { saveStatus } = vnode.state;

    if (saveStatus === "saving") {
      return m("span.text-muted.small", "Saving…");
    }

    if (saveStatus === "saved") {
      return m("span.text-success.small", [
        m("i.fa.fa-check.me-1[aria-hidden=true]"),
        "Saved",
      ]);
    }

    return null;
  },

  renderExpiration(vnode) {
    const { state } = vnode;
    const isCustom = state.preset === PRESET_CUSTOM;
    let summary = getExpirationSummary(state.formExpiresAt);

    if (state.preset === PRESET_CHOOSE) {
      summary = "Choose when the new link should expire.";
    } else if (isCustom && !state.formExpiresAt) {
      summary = "Choose an expiration date.";
    }

    return m(".mb-3", [
      m(".d-flex.justify-content-between.align-items-center.mb-1", [
        m("label.form-label.mb-0[for=share-expiration]", "Expiration"),
        this.renderSaveStatus(vnode),
      ]),
      m("select.form-select#share-expiration", {
        value: state.preset,
        disabled: state.loading,
        onchange: (event) => this.setPreset(vnode, event.target.value),
      }, [
        state.preset === PRESET_CHOOSE && m("option", { value: PRESET_CHOOSE }, "Choose expiration…"),
        ...EXPIRATION_PRESETS.map((preset) => m(
          "option",
          { value: preset.value },
          preset.label
        )),
      ]),
      isCustom && m(Input, {
        type: "datetime-local",
        value: state.formExpiresAt,
        className: "mt-2",
        oninput: (event) => this.setCustomExpiration(vnode, event.target.value),
      }),
      state.expirationError && m(".text-danger.small.mt-1", state.expirationError),
      m(".form-text", summary),
    ]);
  },

  renderCreateBody(vnode) {
    const isDirectory = vnode.attrs.type === "directory";
    return m(".mb-3", [
      m("p", isDirectory
        ? "Create a public sharing link for this directory and choose when it expires."
        : "Create a public sharing link for this file and choose when it expires."),
      this.renderExpiration(vnode),
    ]);
  },

  renderStatusNotice(vnode) {
    const status = resolveShareStatus(vnode.state.share);

    if (status === STATUS_EXPIRED) {
      return m(".alert.alert-warning", [
        m("p.mb-1", "This public link has expired and can no longer be opened."),
        m("p.mb-0", "Choose a new expiration below to reactivate it. Changes are applied automatically."),
      ]);
    }

    if (status === STATUS_REVOKED) {
      return m(".alert.alert-secondary", [
        m("p.mb-1", "This public link has been revoked and can no longer be opened."),
        m("p.mb-0", "Choose an expiration below (or \"Never expires\") to create a new link. Changes are applied automatically."),
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
    ]);
  },

  renderBody(vnode) {
    const { state } = vnode;
    return m(".modal-body", [
      state.error && m(".alert alert-danger", state.error),
      state.copyError && m(".alert alert-warning", state.copyError),
      state.revoked && m(".alert alert-success", "The share link has been revoked."),
      state.share && this.renderStatusNotice(vnode),
      !state.share && !state.loading && this.renderCreateBody(vnode),
      state.share && this.renderShareLink(vnode),
      state.share && this.renderExpiration(vnode),
      state.loading && m(".spinner-border text-primary", {}),
    ]);
  },

  renderFooter(vnode) {
    const { state } = vnode;

    if (!state.share) {
      return m(".modal-footer", [
        m(Button, {
          type: "button",
          class: "btn-secondary",
          onclick: () => closeModal(vnode.attrs.modalId),
        }, "Cancel"),
        m(Button, {
          type: "submit",
          disabled: state.loading,
        }, "Create link"),
      ]);
    }

    return m(".modal-footer", [
      m(Button, {
        type: "button",
        class: "btn-outline-danger me-auto",
        disabled: state.loading || state.saving,
        onclick: () => this.revoke(vnode),
      }, "Revoke"),
      m(Button, {
        type: "button",
        class: "btn-secondary",
        onclick: () => closeModal(vnode.attrs.modalId),
      }, "Close"),
    ]);
  },

  view(vnode) {
    const { type } = vnode.attrs;
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
                if (state.share) {
                  this.commitCustomExpiration(vnode);
                } else {
                  this.submit(vnode);
                }
              },
            }, [
              this.renderBody(vnode),
              this.renderFooter(vnode),
            ]),
          ])
        ),
      )
    );
  }
};

export { ShareDirectoryModal, isShareActive, resolveShareStatus };
