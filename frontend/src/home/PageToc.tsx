import { useEffect, useRef, useState } from "react";
import { useCurrentAnchor } from "../blocks/useCurrentAnchor";
import type { TocEntry } from "../blocks/toc";

const WIDE = "screen and (min-width: 1024px)";

function useWide(): boolean {
  const query = () => typeof window.matchMedia === "function" && window.matchMedia(WIDE).matches;
  const [wide, setWide] = useState(query);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia(WIDE);
    const onChange = () => setWide(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return wide;
}

/**
 * The one contents of a page made of several sections. Wide screens (>= 1024px): a sticky rail on the left
 * that follows the whole page, the section being read highlighted. Narrow: a folded list
 * above the first section.
 */
export function PageToc({ entries }: { entries: TocEntry[] }) {
  const wide = useWide();
  const current = useCurrentAnchor(entries, true);
  const nav = useRef<HTMLElement>(null);
  // The rail scrolls on its own when it is taller than the screen: keep the current entry in view
  // (moving the rail only, never the page).
  useEffect(() => {
    const rail = nav.current;
    const link = rail?.querySelector<HTMLElement>('a[aria-current="location"]');
    if (!rail || !link || !wide) return;
    if (link.offsetTop < rail.scrollTop || link.offsetTop + link.offsetHeight > rail.scrollTop + rail.clientHeight) {
      rail.scrollTop = link.offsetTop - rail.clientHeight / 3;
    }
  }, [current, wide]);
  if (entries.length === 0) return null;
  const list = (
    <ul>
      {entries.map((entry) => (
        <li key={entry.anchor} data-level={entry.level}>
          <a href={`#${entry.anchor}`} aria-current={entry.anchor === current ? "location" : undefined}>
            {entry.text}
          </a>
        </li>
      ))}
    </ul>
  );
  return (
    <nav className="page-toc" aria-label="목차" ref={nav}>
      {wide ? (
        list
      ) : (
        <details>
          <summary>목차</summary>
          {list}
        </details>
      )}
    </nav>
  );
}
