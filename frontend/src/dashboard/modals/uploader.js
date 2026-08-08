import { FsNode, FsNodeList } from "../dashboard";
import { API_V1_FSNODE_TOUCH } from "../urls";
import m from "mithril";


const uploadFile = (e) => (
  Array.from(e.target.files).map((file) => (
    // Create FsNode
    m.request(API_V1_FSNODE_TOUCH, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      params: {
        "path": `${FsNodeList.current.path}/${file.name}`,
      },
    })
    .then((data) => {
      // Update FsNodeList
      const fsNode = new FsNode({...data, ...{upload_status: "uploading"}});
      FsNodeList.addFsNode(fsNode);
      FsNodeList.selectFsNode(fsNode);

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
