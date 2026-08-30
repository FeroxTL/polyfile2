/*
* Updates element styles in browser.
* */
export const reflow = element => {
  element.offsetHeight // eslint-disable-line no-unused-expressions
}

/*
* Check if animations are enabled.
* */
export const checkAnimationsDisabled = () => (
  window.matchMedia(`(prefers-reduced-motion: reduce)`).matches
)
