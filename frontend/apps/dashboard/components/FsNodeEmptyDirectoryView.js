import m from "mithril";
import {uploadFile} from "../modals/uploader";

/*
 * Empty directory component
 */
export const FsNodeEmptyDirectoryView = {
  view() {
    return (
      m(".row",
        m(".col-lg-8 .offset-lg-2",
          m(".card text-center mt-2", [
            m("p.card-header bg-primary", "This directory is empty"),
            m(".card-body border border-primary p-4", [
              m("p.card-text text-secondary", "Select files to upload"),
              m("label.btn btn-primary", [
                m("span.fa fa-upload[aria-hidden=true]"), " ", "Upload",
                m("input.d-none[type=file][multiple]", {onchange: uploadFile}),
              ]),
            ])
          ])
        )
      )
    )
  }
};
