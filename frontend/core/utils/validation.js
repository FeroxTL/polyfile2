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
