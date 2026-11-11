const PERCENT_MAX = 100;
const DEFAULT_RETRY_AFTER_SECONDS = 2;
const MILLISECONDS_PER_SECOND = 1000;

export const ARCHIVE_STATUS = Object.freeze({
  PENDING: "pending",
  RUNNING: "running",
  READY: "ready",
  FAILED: "failed",
  CANCELLED: "cancelled",
  EXPIRED: "expired",
});

const ERROR_STATUSES = new Set([
  ARCHIVE_STATUS.FAILED,
  ARCHIVE_STATUS.CANCELLED,
  ARCHIVE_STATUS.EXPIRED,
]);

const TERMINAL_STATUSES = new Set([
  ARCHIVE_STATUS.READY,
  ...ERROR_STATUSES,
]);

const STATUS_ERROR_MESSAGES = {
  [ARCHIVE_STATUS.FAILED]: "The archive could not be prepared.",
  [ARCHIVE_STATUS.CANCELLED]: "The archive was cancelled.",
  [ARCHIVE_STATUS.EXPIRED]: "This archive has expired. Prepare a new one.",
};

const toNumber = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
};

/**
 * State of an asynchronous directory archive job.
 *
 * The backend reports both ``status`` and the legacy ``state`` key; this model
 * accepts either so callers never have to care which endpoint produced it.
 */
export class ArchiveJob {
  constructor(data = {}) {
    this.job_id = data.job_id || "";
    this.status = data.status || data.state || ARCHIVE_STATUS.PENDING;
    this.root_node_name = data.root_node_name || "";
    this.total_files = toNumber(data.total_files);
    this.processed_files = toNumber(data.processed_files);
    this.total_bytes = toNumber(data.total_bytes);
    this.processed_bytes = toNumber(data.processed_bytes);
    this.last_error = data.last_error || "";
    this.retry_after = toNumber(data.retry_after) || DEFAULT_RETRY_AFTER_SECONDS;
    this.status_url = data.status_url || "";
    this.file_url = data.file_url || data.download_url || "";
    this.expires_at = data.expires_at || null;
  }

  get is_ready() {
    return this.status === ARCHIVE_STATUS.READY && Boolean(this.file_url);
  }

  get has_failed() {
    return ERROR_STATUSES.has(this.status);
  }

  get is_terminal() {
    return TERMINAL_STATUSES.has(this.status);
  }

  get progress_percent() {
    if (this.total_files <= 0) {
      return null;
    }
    return Math.min(
      PERCENT_MAX,
      Math.round((this.processed_files / this.total_files) * PERCENT_MAX),
    );
  }

  get retry_delay_ms() {
    return Math.max(1, this.retry_after) * MILLISECONDS_PER_SECOND;
  }

  get error_message() {
    return (
      this.last_error
      || STATUS_ERROR_MESSAGES[this.status]
      || "The archive is no longer available."
    );
  }
}

export { PERCENT_MAX };
