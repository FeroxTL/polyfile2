import { DashboardFsNodeList } from "../services/DashboardFsNodeList";
import { UploadManager } from "../services/UploadManager";

/**
 * Hand the selected files to the upload queue.
 *
 * The target directory is captured at selection time so a later navigation
 * cannot move an in-flight upload to another folder.
 *
 * @param {Event} event - Change event from a file input.
 * @returns {void}
 */
const uploadFile = (event) => {
  const files = Array.from(event?.target?.files || []);
  if (files.length === 0) {
    return;
  }

  const parentId = DashboardFsNodeList.current?.id ?? null;
  UploadManager.enqueueFiles(files, parentId);

  // Allow selecting the same file again after a conflict or cancellation.
  event.target.value = "";
};

export { uploadFile };
