const DATE_SLICE_LOCALTIME = 16;

const MS_PER_SECOND = 1000;
const SECONDS_PER_MINUTE = 60;
const MINUTES_PER_HOUR = 60;
const HOURS_PER_DAY = 24;
const MS_PER_MINUTE = SECONDS_PER_MINUTE * MS_PER_SECOND;
const MS_PER_HOUR = MINUTES_PER_HOUR * MS_PER_MINUTE;
const MS_PER_DAY = HOURS_PER_DAY * MS_PER_HOUR;

const DAYS_PER_WEEK = 7;
const DAYS_PER_MONTH = 30;
const DAYS_PER_YEAR = 365;
const MONTHS_PER_HALF_YEAR = 6;
const MONTHS_PER_YEAR = 12;

const PRESET_NEVER = "never";
const PRESET_CUSTOM = "custom";

const EXPIRATION_PRESETS = [
  { value: PRESET_NEVER, label: "Never expires" },
  { value: "1h", label: "1 hour", durationMs: MS_PER_HOUR },
  { value: "1d", label: "1 day", durationMs: MS_PER_DAY },
  { value: "7d", label: "7 days", durationMs: DAYS_PER_WEEK * MS_PER_DAY },
  { value: "30d", label: "30 days", durationMs: DAYS_PER_MONTH * MS_PER_DAY },
  { value: "6m", label: "6 months", months: MONTHS_PER_HALF_YEAR },
  { value: "1y", label: "1 year", months: MONTHS_PER_YEAR },
  { value: PRESET_CUSTOM, label: "Custom…" },
];

const RELATIVE_UNITS = [
  { unit: "year", ms: DAYS_PER_YEAR * MS_PER_DAY },
  { unit: "month", ms: DAYS_PER_MONTH * MS_PER_DAY },
  { unit: "day", ms: MS_PER_DAY },
  { unit: "hour", ms: MS_PER_HOUR },
  { unit: "minute", ms: MS_PER_MINUTE },
];

/**
 * Convert an ISO timestamp to the local value expected by datetime-local inputs.
 */
const toDateTimeLocalValue = (value) => {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  date.setMinutes(date.getMinutes() - date.getTimezoneOffset());
  return date.toISOString().slice(0, DATE_SLICE_LOCALTIME);
};

/**
 * Convert a datetime-local value to an ISO timestamp, or null to clear expiration.
 */
const toExpiresAt = (value) => {
  if (!value) {
    return null;
  }

  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
};

/**
 * Build the absolute date for a preset, relative to ``now``.
 */
const getPresetDate = (preset, now = new Date()) => {
  const date = new Date(now.getTime());

  if (preset.durationMs) {
    date.setTime(date.getTime() + preset.durationMs);
  }
  if (preset.months) {
    date.setMonth(date.getMonth() + preset.months);
  }

  return date;
};

const formatExpirationDate = (date) => new Intl.DateTimeFormat([], {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
}).format(date);

const formatRelativeExpiration = (date, now = Date.now()) => {
  const diffMs = date.getTime() - now;

  if (Math.abs(diffMs) < MS_PER_MINUTE) {
    return diffMs >= 0 ? "in less than a minute" : "less than a minute ago";
  }

  const formatter = new Intl.RelativeTimeFormat([], { numeric: "auto" });
  const { unit, ms } = RELATIVE_UNITS.find(
    (relativeUnit) => Math.abs(diffMs) >= relativeUnit.ms
  ) || RELATIVE_UNITS[RELATIVE_UNITS.length - 1];

  return formatter.format(Math.round(diffMs / ms), unit);
};

/**
 * Human-readable summary shown under the expiration control.
 */
const getExpirationSummary = (value, now = Date.now()) => {
  if (!value) {
    return "Link will not expire.";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Choose an expiration date.";
  }

  const prefix = date.getTime() <= now ? "Expired" : "Expires";
  return `${prefix} on ${formatExpirationDate(date)} (${formatRelativeExpiration(date, now)}).`;
};

/**
 * Validate a datetime-local value. Returns an error message or null.
 */
const validateExpiration = (value, now = Date.now()) => {
  if (!value) {
    return "Choose an expiration date.";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Enter a valid date and time.";
  }
  if (date.getTime() <= now) {
    return "Expiration must be in the future.";
  }

  return null;
};

export {
  EXPIRATION_PRESETS,
  PRESET_CUSTOM,
  PRESET_NEVER,
  getExpirationSummary,
  getPresetDate,
  toDateTimeLocalValue,
  toExpiresAt,
  validateExpiration,
};
