import m from "mithril";

/*
* Bootstrap Input.
*
* Supports either a Mithril stream or a plain value:
*   m(Input, { stream: valueStream })
*   m(Input, { value: "Read only text", readOnly: true })
* */
const getClassName = (attrs) => [
  attrs.class,
  attrs.className,
  Array.isArray(attrs.errors) && attrs.errors.length ? "is-invalid" : null,
].filter(Boolean).join(" ");

const Input = {
  view(vnode) {
    const {
      autofocus,
      errors,
      oninput,
      placeholder,
      readOnly,
      required,
      stream,
      type,
      value,
      disabled,
    } = vnode.attrs;

    const hasStream = typeof stream === "function";
    const hasValue = value !== null && typeof value !== "undefined";

    if (!hasStream && !hasValue) {
      throw new Error("Argument 'stream' or 'value' is required");
    }

    return [
      m("input.form-control", {
        type,
        value: hasStream ? stream() : value,
        class: getClassName(vnode.attrs) || null,
        required,
        placeholder,
        readOnly,
        disabled,
        oncreate: (inputVnode) => {
          if (autofocus) {
            inputVnode.dom.focus();
          }
        },
        oninput: (event) => {
          if (hasStream) {
            stream(event.target.value);
          }
          if (oninput) {
            oninput(event);
          }
        },
      }),
      Array.isArray(errors) && errors.map((error) => (m(".invalid-feedback", error))),
    ];
  }
};

export { Input };
