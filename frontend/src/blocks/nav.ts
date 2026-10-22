// Moving around inside one document: what a CTA button needs from the view that shows it.
import { createContext, useContext } from "react";
import type { Block, Document } from "./types";

export interface DocumentNav {
  /** Open the tab holding the block and scroll to it. */
  openBlock: (blockId: string) => void;
  /** Open the tab and scroll to its top. */
  openTab: (tabId: string) => void;
  /** Where a target lives, for paper: "탭 제목 · 블록 제목" (just the tab for a tab target). */
  describe: (target: InternalTarget) => string | null;
}

export type InternalTarget = { kind: "block"; block_id: string } | { kind: "tab"; tab_id: string };

const none: DocumentNav = { openBlock: () => {}, openTab: () => {}, describe: () => null };

export const DocumentNavContext = createContext<DocumentNav>(none);

export function useDocumentNav(): DocumentNav {
  return useContext(DocumentNavContext);
}

function titleOf(block: Block): string | null {
  return "title" in block && typeof block.title === "string" && block.title ? block.title : null;
}

/** "탭 제목 · 블록 제목" for a target of this document, or null when it is not there. */
export function describeTarget(document: Document, target: InternalTarget): string | null {
  if (target.kind === "tab") {
    return document.tabs.find((tab) => tab.id === target.tab_id)?.title ?? null;
  }
  for (const tab of document.tabs) {
    const block = tab.blocks.find((b) => b.id === target.block_id);
    if (block) return [tab.title, titleOf(block)].filter(Boolean).join(" · ");
  }
  return null;
}
