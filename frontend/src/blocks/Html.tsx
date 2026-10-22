import { Heading } from "./Heading";
import type { HtmlBlock } from "./types";

/**
 * Exception block. `html` was cleaned against an allow-list when the document was stored
 * (backend/documents/sanitize.py), so it is set as is; nothing else in the app does this.
 */
export function Html({ block, anchor }: { block: HtmlBlock; anchor: string }) {
  return (
    <section className="block-html">
      {block.title && (
        <Heading level={block.level ?? 2} id={anchor}>
          {block.title}
        </Heading>
      )}
      <div className="prose" dangerouslySetInnerHTML={{ __html: block.html }} />
    </section>
  );
}
