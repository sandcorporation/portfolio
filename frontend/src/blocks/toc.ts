import { entryFor, type TocTitle } from "./registry";
import type { Tab } from "./types";

export interface TocEntry extends TocTitle {
  anchor: string;
}

export function anchorFor(prefix: string, blockId: string): string {
  return `${prefix}${blockId}`;
}

/** Computed from block titles at render time; never stored. */
export function tableOfContents(tab: Tab, prefix: string): TocEntry[] {
  return tab.blocks.flatMap((block) => {
    const title = entryFor(block)?.toc?.(block);
    return title ? [{ ...title, anchor: anchorFor(prefix, block.id) }] : [];
  });
}
