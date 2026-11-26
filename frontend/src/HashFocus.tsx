import { useEffect } from "react";
import { focusHashTarget } from "./anchorFocus";

/** Re-aim at the hash target once React has drawn (issue 48); a frame later too, for late layout. */
export function HashFocus() {
  useEffect(() => {
    if (!window.location.hash) return;
    focusHashTarget();
    const frame = requestAnimationFrame(() => focusHashTarget());
    return () => cancelAnimationFrame(frame);
  }, []);
  return null;
}
