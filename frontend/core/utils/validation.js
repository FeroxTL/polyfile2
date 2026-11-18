/**
 * Checks for the presence of attributes and throws an error if any are missing.
 * @param {Object} obj - The object to check.
 * @param {string[]} attributes - A list of attribute names.
 * @throws {Error} - If any attribute is missing.
 */
export function validateAttributes(obj, attributes) {
  for (const attr of attributes) {
    if (!(attr in obj)) {
      throw new Error(`Error: Attribute "${attr}" is missing from the object.`);
    }
  }
  return true;
}

export function ensureAttribute(value) {
  if (typeof value === "undefined") {
    throw new Error(`Error: Attribute is missing from the object.`);
  }
  return value;
}

/*
 * Mirrors `polyfile/apps/storage/schemas.py`: cross-platform reserved
 * characters and the FsNode.name length limit.
 */
const RESERVED_FS_NODE_NAME_CHARACTERS = /[<>:"/\\|?*]/u;
const MAX_FS_NODE_NAME_LENGTH = 255;

/**
 * Validate a file or directory name before sending it to the backend.
 *
 * @param {string} name - Proposed FsNode name.
 * @returns {string[]} Human-readable validation errors (empty when valid).
 */
export function getFsNodeNameErrors(name) {
  if (!name) {
    return ["Name is required"];
  }
  if (name.length > MAX_FS_NODE_NAME_LENGTH) {
    return [`Name is too long (${MAX_FS_NODE_NAME_LENGTH} characters max)`];
  }
  if (name === "." || name === "..") {
    return ['Directory name can not be "." or ".."'];
  }
  if (RESERVED_FS_NODE_NAME_CHARACTERS.test(name)) {
    return ['Name contains reserved characters: < > : " / \\ | ? *'];
  }
  return [];
}
