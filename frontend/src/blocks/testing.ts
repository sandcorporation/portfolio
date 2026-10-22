// Test helpers for block renderer tests. The example document is the same file the backend
// validation tests read (fixtures/documents/ at the repo root).
import example from "../../../fixtures/documents/example-proposal.json";
import type { Block, Document } from "./types";

// JSON imports widen string literals, so the fixture is typed by hand; the backend tests
// prove it is a valid document.
export const exampleDocument = example as unknown as Document;

export function exampleBlock<T extends Block["type"]>(id: string, type: T): Extract<Block, { type: T }> {
  const block = exampleDocument.tabs.flatMap((tab) => tab.blocks).find((b) => b.id === id);
  if (!block || block.type !== type) throw new Error(`no ${type} block "${id}" in the example`);
  return block as Extract<Block, { type: T }>;
}

/** A one-tab document holding just these blocks. */
export function documentOf(...blocks: Block[]): Document {
  return { tabs: [{ id: "main", title: "본문", blocks }] };
}
