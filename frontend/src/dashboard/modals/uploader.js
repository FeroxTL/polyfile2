import m from "mithril";
import { FsNodeList, FsNode } from "../dashboard";
import { API_V1_FSNODE_TOUCH } from "../urls";


function uploadFile(e) {
  Array.from(e.target.files).map((file) => {
    // Create FsNode
    m.request({
      method: "POST",
      url: API_V1_FSNODE_TOUCH,
      headers: {
        "Content-Type": "application/json",
      },
      params: {
        "path": FsNodeList.current.path + "/" + file.name,
      },
    })
    .then((data) => {
      // Update FsNodeList
      const fsNode = new FsNode(data);
      FsNodeList.addFsNode(fsNode);
      FsNodeList.selectFsNode(fsNode);

      // Upload file content
      return m.request({
        method: "POST",
        url: data.upload_url,
        body: file,
        // Bypasses default JSON.stringify
        serialize: (value) => value,
      }).then((data) => {
        Object.assign(fsNode, data);
      })
    })
    .catch((error) => {
      console.log('err', error)  // TODO: error handling
    });
  })
}

export { uploadFile };
