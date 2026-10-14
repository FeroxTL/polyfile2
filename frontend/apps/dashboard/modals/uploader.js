import {joinPath} from "@polyfile/core/utils/urls";
import {DashboardFsNode} from "../models/DashboardFsNode";
import {DashboardFsNodeList} from "../services/DashboardFsNodeList";
import { API_V1_FSNODE_TOUCH } from "../constants/endpoints";
import m from "mithril";


// TODO: do we need selection of uploaded nodes? I think no.
//  Maybe we should show them as "new files"
const uploadFile = (e) => (
  Array.from(e.target.files).map((file) => (
    // Create FsNode
    m.request(API_V1_FSNODE_TOUCH, {
      method: "POST",
      headers: {
        "Content-Type": "core/json",
      },
      params: {
        "path": joinPath(DashboardFsNodeList.current.path, file.name),
      },
    })
    .then((data) => {
      // Update FsNodeList
      const fsNode = new DashboardFsNode({...data, upload_status: "uploading"});
      DashboardFsNodeList.addFsNode(fsNode);
      DashboardFsNodeList.selectFsNode(fsNode);

      // Upload file content
      m.request(data.upload_url, {
        method: "POST",
        // Send binary data
        body: file,
        // Bypasses default JSON.stringify
        serialize: (value) => value,
      }).then((uploadData) => {
        Object.assign(fsNode, uploadData);
        fsNode.upload_status = "done";
      });
      return data;
    })
    .catch((error) => {
      // TODO: error handling
      console.log('err', error);
    })
  ))
)

export { uploadFile };
