/** After React draws over the server HTML (issue 109), the browser's own hash scroll has already
 * happened against the old DOM, so the target may have moved and focus stays at the document start.
 * Scroll to the `location.hash` target again and move focus there so the next Tab continues inside it. */
export function focusHashTarget(): boolean {
  const id = decodeURIComponent(window.location.hash.slice(1));
  if (!id) return false;
  const target = document.getElementById(id);
  if (!target) return false;
  if (!target.hasAttribute("tabindex") && !target.matches("a[href], button, input, select, textarea")) {
    target.setAttribute("tabindex", "-1");
  }
  target.focus({ preventScroll: true });
  target.scrollIntoView?.();
  return true;
}
