// One entry per block type. The mapped type makes `tsc` fail until every block type in the
// generated schema has a renderer here, so a new Pydantic block cannot ship without one.
import type { ComponentType } from "react";
import { CaseRef } from "./CaseRef";
import { Callout } from "./Callout";
import { Cover } from "./Cover";
import { Details } from "./Details";
import { Gallery } from "./Gallery";
import { Kpi } from "./Kpi";
import { MarkdownSection } from "./MarkdownSection";
import { Table } from "./Table";
import type { Block, BlockType } from "./types";

export interface TocTitle {
  text: string;
  level: 2 | 3;
}

export interface BlockEntry<B extends Block> {
  /** `anchor` is the DOM id the block's heading must carry so the TOC can link to it. */
  Render: ComponentType<{ block: B; anchor: string }>;
  /** The block's line in the table of contents, if it has one. */
  toc?: (block: B) => TocTitle | null;
}

type Registry = { [K in BlockType]: BlockEntry<Extract<Block, { type: K }>> };

const titled =
  (level: 2 | 3) =>
  (block: { title?: string | null }): TocTitle | null =>
    block.title ? { text: block.title, level } : null;

export const registry: Registry = {
  cover: { Render: Cover },
  kpi: { Render: Kpi, toc: titled(3) },
  markdown: {
    Render: MarkdownSection,
    toc: (block) => (block.title ? { text: block.title, level: block.level ?? 2 } : null),
  },
  table: { Render: Table, toc: titled(3) },
  callout: { Render: Callout },
  details: { Render: Details },
  gallery: { Render: Gallery, toc: titled(3) },
  "case-ref": { Render: CaseRef, toc: titled(3) },
};

/** The entry for a block, or null for a type this build does not know (newer data). */
export function entryFor(block: { type: string }): BlockEntry<Block> | null {
  if (!Object.hasOwn(registry, block.type)) return null;
  // The registry is keyed by `type`, so the entry matches this block's own type.
  return registry[block.type as BlockType] as BlockEntry<Block>;
}
