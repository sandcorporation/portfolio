import { useEffect, useState } from "react";
import type { TocEntry } from "./toc";

/** The last heading that has scrolled past the sticky chrome, or the first one before any has. */
export function useCurrentAnchor(entries: TocEntry[], enabled: boolean): string | null {
  const [current, setCurrent] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled || entries.length === 0) return;
    let frame = 0;
    const update = () => {
      frame = 0;
      const line = window.innerHeight * 0.25;
      let found = entries[0]?.anchor ?? null;
      for (const entry of entries) {
        const el = window.document.getElementById(entry.anchor);
        if (el && el.getBoundingClientRect().top <= line) found = entry.anchor;
      }
      setCurrent(found);
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [entries, enabled]);
  return current;
}
