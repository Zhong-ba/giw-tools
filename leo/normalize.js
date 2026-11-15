const { aliases } = require("./dataSchema.json");

/**
 * Returns the canonical raw field name for a table (see dataSchema.json),
 * unless the object already has the canonical field.
 */
function canonicalKey(excel, key, item) {
  const target = aliases[excel]?.[key];
  return target && !(target in item) ? target : key;
}

/**
 * Some sources store single-precision floats widened to double (0.05000000074505806).
 * Returns the shortest decimal that rounds to the same float32; other numbers are unchanged.
 */
function tidyNumber(value) {
  if (typeof value !== "number" || Number.isInteger(value) || Math.fround(value) !== value) return value;
  for (let digits = 1; digits <= 9; digits++) {
    const candidate = Number(value.toPrecision(digits));
    if (Math.fround(candidate) === value) return candidate;
  }
  return value;
}

module.exports = { canonicalKey, tidyNumber };
