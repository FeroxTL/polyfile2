import { FsNode, FsNodeList } from "../dashboard";
import { API_V1_FSNODE_TOUCH } from "../urls";
import m from "mithril";


const uploadFile = (e) => {
  Array.from(e.target.files).map((file) => (
    // Create FsNode
    m.request({
      method: "POST",
      url: API_V1_FSNODE_TOUCH,
      headers: {
        "Content-Type": "application/json",
      },
      params: {
        "path": `${FsNodeList.current.path}/${file.name}`,
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
      }).then((uploadData) => {
        Object.assign(fsNode, uploadData);
      })
    })
    .catch((error) => {
      // TODO: error handling
      console.log('err', error);
    })
  ));
}

export { uploadFile };
