import m from "mithril";

const Input = {
  view(vnode) {
    if (!vnode.attrs.stream) {
      throw new Error("Argument 'stram' is required")
    }

    const { errors, required, stream } = vnode.attrs;

    return [
      m("input[type=text].form-control", {
        oncreate: () => vnode.attrs.autofocus && vnode.dom.focus(),
        value: stream(),
        class: Array.isArray(errors) && errors.length ? "is-invalid" : "",
        required,
        oninput: (event) => {
          stream(event.target.value);
          if (vnode.attrs.oninput) {
            vnode.attrs.oninput(event);
          };
        },
      }),
      errors && errors.map((error) => (m(".invalid-feedback", error))),
    ]
  }
};

export default Input;
