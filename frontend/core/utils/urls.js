/**
 * Joins multiple path segments into a single path string.
 *
 * This function mimics the behavior of Node.js `path.join()`
 * for browser environments. It ensures that:
 * 1. Segments are joined by a single forward slash (/).
 * 2. Trailing slashes from all segments are removed.
 * 3. Leading slashes from all segments EXCEPT the first one are removed
 *    to prevent double slashes (e.g., "foo//bar") while preserving
 *    absolute paths (e.g., "/foo/bar").
 * 4. Empty strings or null/undefined values are ignored.
 *
 * @param {...string} parts - The path segments to join.
 * @returns {string} The joined path string.
 *
 * @example
 * // Returns "foo/bar"
 * joinPath("foo/", "/bar");
 *
 * @example
 * // Returns "/foo/bar"
 * joinPath("/", "foo/", "/bar");
 *
 * @example
 * // Returns "/foo/bar" (Preserves leading slash of first part)
 * joinPath("/foo", "bar");
 *
 * @example
 * // Returns "folder/subfolder"
 * joinPath("folder/", "subfolder", "");
 */
export function joinPath(...parts) {
  return parts
    .filter(part => part !== null && typeof part !== "undefined" && part !== "")
    .map((part, index) => {
      const str = String(part);
      if (index === 0) {
        const trimmed = str.replace(/[\\/]+$/u, "");
        // For the first part, only trim trailing slashes
        return (trimmed === "" && str.indexOf("/") !== -1) ? "" : trimmed;
      }
      // For all other parts, trim both leading and trailing slashes
      return str.replace(/^[\\/]+|[\\/]+$/ug, "");
    })
    // Join with a single forward slash
    .join("/");
}

/**
 * Percent-encodes every segment of a slash-separated path.
 *
 * Path separators are preserved so the result can be interpolated into
 * Mithril's variadic `:path...` route params, which are not encoded by
 * `m.buildPathname()`.
 *
 * @param {string} path - The path to encode.
 * @returns {string} The encoded path.
 *
 * @example
 * // Returns "/docs/report%20%231.txt"
 * encodePath("/docs/report #1.txt");
 */
export function encodePath(path) {
  return String(path ?? "")
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}
