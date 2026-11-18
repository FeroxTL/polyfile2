const UNKNOWN_ERROR = "Unknown error, please try again later";

const flattenDetail = (detail) => {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.filter(Boolean).join("; ");
  }
  if (detail && typeof detail === "object") {
    return Object.values(detail)
      .flat()
      .filter(Boolean)
      .join("; ");
  }
  return "";
};

/**
 * Extract a displayable message from an `m.request` rejection.
 *
 * Marshmallow validation errors use an object-shaped `detail`
 * (`{name: ["..."]}`), while HTTP exceptions use a string.
 *
 * @param {Object} error - Mithril request error.
 * @returns {string} Human-readable error message.
 */
export function getApiErrorDetail(error) {
  if (!error || error.code === 0 || !error.response) {
    return UNKNOWN_ERROR;
  }

  return flattenDetail(error.response.detail) || UNKNOWN_ERROR;
}
